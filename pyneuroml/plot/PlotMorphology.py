#!/usr/bin/env python3
"""
Utilities to plot NeuroML2 cell morphologies.

File: pyneuroml/plot/PlotMorphology.py

Copyright 2022 NeuroML contributors
"""


import argparse
import os
import sys

import typing
import logging

import numpy as np
from matplotlib import pyplot as plt
from matplotlib_scalebar.scalebar import ScaleBar
import plotly.graph_objects as go

from pyneuroml.pynml import read_neuroml2_file
from pyneuroml.utils.cli import build_namespace
from pyneuroml.plot.utils import LineDataUnits, get_sphere_surface, get_frustrum_surface


logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


DEFAULTS = {
    "v": False,
    "nogui": False,
    "saveToFile": None,
    "interactive3d": False,
    "plane2d": "xy",
    "minwidth": 0.0,
    "square": False,
}


def process_args():
    """
    Parse command-line arguments.
    """
    parser = argparse.ArgumentParser(
        description=("A script which can generate plots of morphologies in NeuroML 2")
    )

    parser.add_argument(
        "nmlFile",
        type=str,
        metavar="<NeuroML 2 file>",
        help="Name of the NeuroML 2 file",
    )

    parser.add_argument(
        "-v", action="store_true", default=DEFAULTS["v"], help="Verbose output"
    )

    parser.add_argument(
        "-nogui",
        action="store_true",
        default=DEFAULTS["nogui"],
        help="Don't open plot window",
    )

    parser.add_argument(
        "-plane2d",
        type=str,
        metavar="<plane, e.g. xy, yz, zx>",
        default=DEFAULTS["plane2d"],
        help="Plane to plot on for 2D plot",
    )

    parser.add_argument(
        "-minWidth",
        action="store_true",
        default=DEFAULTS["minwidth"],
        help="Minimum width of lines to use",
    )

    parser.add_argument(
        "-interactive3d",
        action="store_true",
        default=DEFAULTS["interactive3d"],
        help="Show interactive 3D plot",
    )

    parser.add_argument(
        "-saveToFile",
        type=str,
        metavar="<Image file name>",
        default=None,
        help="Name of the image file",
    )

    parser.add_argument(
        "-square",
        action="store_true",
        default=DEFAULTS["square"],
        help="Scale axes so that image is approximately square",
    )

    return parser.parse_args()


def main(args=None):
    if args is None:
        args = process_args()

    plot_from_console(a=args)


def plot_from_console(a: typing.Optional[typing.Any] = None, **kwargs: str):
    """Wrapper around functions for the console script.

    :param a: arguments object
    :type a:
    :param **kwargs: other arguments
    """
    a = build_namespace(DEFAULTS, a, **kwargs)
    print(a)
    if a.interactive3d:
        plot_interactive_3D_matplotlib(a.nml_file, a.v, a.nogui, a.save_to_file)
    else:
        plot_2D(
            a.nml_file, a.plane2d, a.minwidth, a.v, a.nogui, a.save_to_file, a.square
        )


def plot_2D(
    nml_file: str,
    plane2d: str = "xy",
    min_width: float = DEFAULTS["minwidth"],  # type: ignore
    verbose: bool = False,
    nogui: bool = False,
    save_to_file: typing.Optional[str] = None,
    square: bool = False,
):
    """Plot cell morphology in 2D.

    This uses matplotlib to plot the morphology in 2D.

    :param nml_file: path to NeuroML cell file
    :type nml_file: str
    :param plane2d: what plane to plot (xy/yx/yz/zy/zx/xz)
    :type plane2d: str
    :param min_width: minimum width for segments (useful for visualising very
        thin segments): default 0.8um
    :type min_width: float
    :param verbose: show extra information (default: False)
    :type verbose: bool
    :param nogui: do not show matplotlib GUI (default: false)
    :type nogui: bool
    :param save_to_file: optional filename to save generated morphology to
    :type save_to_file: str
    :param square: scale axes so that image is approximately square
    :type square: bool
    """

    if verbose:
        print("Plotting %s" % nml_file)

    nml_model = read_neuroml2_file(
        nml_file,
        include_includes=True,
        check_validity_pre_include=False,
        verbose=False,
        optimized=True,
    )

    from pyneuroml.utils import extract_position_info

    (
        cell_id_vs_cell,
        pop_id_vs_cell,
        positions,
        pop_id_vs_color,
        pop_id_vs_radii,
    ) = extract_position_info(nml_model, verbose)

    title = "2D plot of %s from %s" % (nml_model.networks[0].id, nml_file)

    if verbose:
        print("positions: %s" % positions)
        print("pop_id_vs_cell: %s" % pop_id_vs_cell)
        print("cell_id_vs_cell: %s" % cell_id_vs_cell)
        print("pop_id_vs_color: %s" % pop_id_vs_color)
        print("pop_id_vs_radii: %s" % pop_id_vs_radii)

    fig, ax = plt.subplots(1, 1)  # noqa
    plt.get_current_fig_manager().set_window_title(title)

    ax.set_aspect("equal")

    ax.spines["right"].set_visible(False)
    ax.spines["top"].set_visible(False)
    ax.yaxis.set_ticks_position("left")
    ax.xaxis.set_ticks_position("bottom")

    if plane2d == "xy":
        ax.set_xlabel("x (μm)")
        ax.set_ylabel("y (μm)")
    elif plane2d == "yx":
        ax.set_xlabel("y (μm)")
        ax.set_ylabel("x (μm)")
    elif plane2d == "xz":
        ax.set_xlabel("x (μm)")
        ax.set_ylabel("z (μm)")
    elif plane2d == "zx":
        ax.set_xlabel("z (μm)")
        ax.set_ylabel("x (μm)")
    elif plane2d == "yz":
        ax.set_xlabel("y (μm)")
        ax.set_ylabel("z (μm)")
    elif plane2d == "zy":
        ax.set_xlabel("z (μm)")
        ax.set_ylabel("y (μm)")
    else:
        logger.error(f"Invalid value for plane: {plane2d}")
        sys.exit(-1)

    max_xaxis = -1 * float("inf")
    min_xaxis = float("inf")

    for pop_id in pop_id_vs_cell:
        cell = pop_id_vs_cell[pop_id]
        pos_pop = positions[pop_id]

        for cell_index in pos_pop:
            pos = pos_pop[cell_index]

            try:
                soma_segs = cell.get_all_segments_in_group("soma_group")
            except:
                soma_segs = []
            try:
                dend_segs = cell.get_all_segments_in_group("dendrite_group")
            except:
                dend_segs = []
            try:
                axon_segs = cell.get_all_segments_in_group("axon_group")
            except:
                axon_segs = []

            if cell is None:

                radius = pop_id_vs_radii[pop_id] if pop_id in pop_id_vs_radii else 10
                color = "b"
                if pop_id in pop_id_vs_color:
                    color = pop_id_vs_color[pop_id]

                if plane2d == "xy":
                    min_xaxis, max_xaxis = add_line(
                        ax,
                        [pos[0], pos[0]],
                        [pos[1], pos[1]],
                        radius,
                        color,
                        min_xaxis,
                        max_xaxis,
                    )
                elif plane2d == "yx":
                    min_xaxis, max_xaxis = add_line(
                        ax,
                        [pos[1], pos[1]],
                        [pos[0], pos[0]],
                        radius,
                        color,
                        min_xaxis,
                        max_xaxis,
                    )
                elif plane2d == "xz":
                    min_xaxis, max_xaxis = add_line(
                        ax,
                        [pos[0], pos[0]],
                        [pos[2], pos[2]],
                        radius,
                        color,
                        min_xaxis,
                        max_xaxis,
                    )
                elif plane2d == "zx":
                    min_xaxis, max_xaxis = add_line(
                        ax,
                        [pos[2], pos[2]],
                        [pos[0], pos[0]],
                        radius,
                        color,
                        min_xaxis,
                        max_xaxis,
                    )
                elif plane2d == "yz":
                    min_xaxis, max_xaxis = add_line(
                        ax,
                        [pos[1], pos[1]],
                        [pos[2], pos[2]],
                        radius,
                        color,
                        min_xaxis,
                        max_xaxis,
                    )
                elif plane2d == "zy":
                    min_xaxis, max_xaxis = add_line(
                        ax,
                        [pos[2], pos[2]],
                        [pos[1], pos[1]],
                        radius,
                        color,
                        min_xaxis,
                        max_xaxis,
                    )
                else:
                    raise Exception(f"Invalid value for plane: {plane2d}")

            else:

                for seg in cell.morphology.segments:
                    p = cell.get_actual_proximal(seg.id)
                    d = seg.distal
                    width = (p.diameter + d.diameter) / 2

                    if width < min_width:
                        width = min_width

                    color = "b"
                    if pop_id in pop_id_vs_color:
                        color = pop_id_vs_color[pop_id]
                    else:
                        if seg.id in soma_segs:
                            color = "g"
                        if seg.id in axon_segs:
                            color = "r"

                    spherical = (
                        p.x == d.x
                        and p.y == d.y
                        and p.z == d.z
                        and p.diameter == d.diameter
                    )

                    if verbose:
                        print(
                            "\nSeg %s, id: %s%s has proximal: %s, distal: %s (width: %s, min_width: %s), color: %s"
                            % (
                                seg.name,
                                seg.id,
                                " (spherical)" if spherical else "",
                                p,
                                d,
                                width,
                                min_width,
                                str(color),
                            )
                        )

                    if plane2d == "xy":
                        min_xaxis, max_xaxis = add_line(
                            ax,
                            [pos[0] + p.x, pos[0] + d.x],
                            [pos[1] + p.y, pos[1] + d.y],
                            width,
                            color,
                            min_xaxis,
                            max_xaxis,
                        )
                    elif plane2d == "yx":
                        min_xaxis, max_xaxis = add_line(
                            ax,
                            [pos[1] + p.y, pos[1] + d.y],
                            [pos[0] + p.x, pos[0] + d.x],
                            width,
                            color,
                            min_xaxis,
                            max_xaxis,
                        )
                    elif plane2d == "xz":
                        min_xaxis, max_xaxis = add_line(
                            ax,
                            [pos[0] + p.x, pos[0] + d.x],
                            [pos[2] + p.z, pos[2] + d.z],
                            width,
                            color,
                            min_xaxis,
                            max_xaxis,
                        )
                    elif plane2d == "zx":
                        min_xaxis, max_xaxis = add_line(
                            ax,
                            [pos[2] + p.z, pos[2] + d.z],
                            [pos[0] + p.x, pos[0] + d.x],
                            width,
                            color,
                            min_xaxis,
                            max_xaxis,
                        )
                    elif plane2d == "yz":
                        min_xaxis, max_xaxis = add_line(
                            ax,
                            [pos[1] + p.y, pos[1] + d.y],
                            [pos[2] + p.z, pos[2] + d.z],
                            width,
                            color,
                            min_xaxis,
                            max_xaxis,
                        )
                    elif plane2d == "zy":
                        min_xaxis, max_xaxis = add_line(
                            ax,
                            [pos[2] + p.z, pos[2] + d.z],
                            [pos[1] + p.y, pos[1] + d.y],
                            width,
                            color,
                            min_xaxis,
                            max_xaxis,
                        )
                    else:
                        raise Exception(f"Invalid value for plane: {plane2d}")

                    if verbose:
                        print("Extent x: %s -> %s" % (min_xaxis, max_xaxis))

        # add a scalebar
        # ax = fig.add_axes([0, 0, 1, 1])
        sc_val = 50
        if max_xaxis - min_xaxis < 100:
            sc_val = 5
        if max_xaxis - min_xaxis < 10:
            sc_val = 1
        scalebar1 = ScaleBar(
            0.001,
            units="mm",
            dimension="si-length",
            scale_loc="top",
            location="lower right",
            fixed_value=sc_val,
            fixed_units="um",
            box_alpha=0.8,
        )
        ax.add_artist(scalebar1)

        plt.autoscale()
        xl = plt.xlim()
        yl = plt.ylim()
        if verbose:
            print("Auto limits - x: %s , y: %s" % (xl, yl))

        small = 0.1
        if xl[1] - xl[0] < small and yl[1] - yl[0] < small:  # i.e. only a point
            plt.xlim([-100, 100])
            plt.ylim([-100, 100])
        elif xl[1] - xl[0] < small:
            d_10 = (yl[1] - yl[0]) / 10
            m = xl[0] + (xl[1] - xl[0]) / 2.0
            plt.xlim([m - d_10, m + d_10])
        elif yl[1] - yl[0] < small:
            d_10 = (xl[1] - xl[0]) / 10
            m = yl[0] + (yl[1] - yl[0]) / 2.0
            plt.ylim([m - d_10, m + d_10])

        if square:
            if xl[1] - xl[0] > yl[1] - yl[0]:
                d2 = (xl[1] - xl[0]) / 2
                m = yl[0] + (yl[1] - yl[0]) / 2.0
                plt.ylim([m - d2, m + d2])

            if xl[1] - xl[0] < yl[1] - yl[0]:
                d2 = (yl[1] - yl[0]) / 2
                m = xl[0] + (xl[1] - xl[0]) / 2.0
                plt.xlim([m - d2, m + d2])

    if save_to_file:
        abs_file = os.path.abspath(save_to_file)
        plt.savefig(abs_file, dpi=200, bbox_inches="tight")
        print(f"Saved image on plane {plane2d} to {abs_file} of plot: {title}")

    if not nogui:
        plt.show()


def add_line(ax, xv, yv, width, color, min_xaxis, max_xaxis):

    if (
        abs(xv[0] - xv[1]) < 0.01 and abs(yv[0] - yv[1]) < 0.01
    ):  # looking at the cylinder from the top, OR a sphere, so draw a circle
        xv[1] = xv[1] + width / 1000.0
        yv[1] = yv[1] + width / 1000.0

        ax.add_line(
            LineDataUnits(xv, yv, linewidth=width, solid_capstyle="round", color=color)
        )

    ax.add_line(
        LineDataUnits(xv, yv, linewidth=width, solid_capstyle="butt", color=color)
    )

    min_xaxis = min(min_xaxis, xv[0])
    min_xaxis = min(min_xaxis, xv[1])
    max_xaxis = max(max_xaxis, xv[0])
    max_xaxis = max(max_xaxis, xv[1])
    return min_xaxis, max_xaxis


def plot_interactive_3D(
    nml_file: str,
    verbose: bool = False,
    nogui: bool = False,
    engine: str = "matplotlib",
    save_to_file: typing.Optional[str] = None,
):
    """Plot morphology interactively using a provided engine.

    The engines available are:

    - matplotlib: 3D plot using lines of constant widths in Matplotlib
    - matplotlib_surface: 3D plot using surfaces in Matplotlib
    - plotly: 3D plot using lines of constant widths using Plotly, for viewing
      in web browsers
    - plotly_surface: 3D plot using surfaces in Plotly, for viewing in web
      browsers

    In terms of performance, the surface plots require more computational
    resources since these plot 3D surfaces that contain a much larger number of
    points than their naive couterparts.

    Between Matplotlib and Plotly, Matplotlib performs better.

    :param nml_file: path to NeuroML cell file
    :type nml_file: str
    :param verbose: show extra information (default: False)
    :type verbose: bool
    :param nogui: do not show GUI (default: false)
    :type nogui: bool
    :param engine: plotting engine to use
    :type engine: str
    :param save_to_file: optional filename to save generated morphology to
    :type save_to_file: str
    """
    if engine == "matplotlib_surface":
        plot_interactive_3D_matplotlib(nml_file, verbose, nogui, save_to_file)
    elif engine == "matplotlib":
        plot_interactive_3D_matplotlib_naive(nml_file, verbose, nogui, save_to_file)
    elif engine == "plotly":
        plot_interactive_3D_web_naive(
            nml_file, verbose, nogui, save_to_file=save_to_file
        )
    elif engine == "plotly_surface":
        plot_interactive_3D_web(nml_file, verbose, nogui, save_to_file)


def plot_interactive_3D_matplotlib_naive(
    nml_file: str,
    verbose: bool = False,
    nogui: bool = False,
    save_to_file: typing.Optional[str] = None,
):
    """Plot NeuroML2 cell morphology interactively using matplotlib lines.

    These plots are limited to cylinders and spheres only. So, they will not
    show segments that are frustrums (different proximan and distal diameters).

    :param nml_file: path to NeuroML cell file
    :type nml_file: str
    :param verbose: show extra information (default: False)
    :type verbose: bool
    :param nogui: do not show matplotlib GUI (default: false)
    :type nogui: bool
    :param save_to_file: optional filename to save generated morphology to
    :type save_to_file: str
    """
    nml_model = read_neuroml2_file(nml_file)

    fig = plt.figure()
    ax = fig.add_subplot(projection="3d")
    ax.set_xlabel("extent (um)")
    ax.set_ylabel("extent (um)")
    ax.set_zlabel("extent (um)")

    for cell in nml_model.cells:
        title = f"3D plot of {cell.id} from {nml_file}"

        logger.info(
            f"Plotting morphology of cell {cell.id} from {nml_file} with {len(cell.morphology.segments)} segments"
        )
        for seg in cell.morphology.segments:
            p = cell.get_actual_proximal(seg.id)
            d = seg.distal
            if verbose:
                print(
                    f"\nSegment {seg.name}, id: {seg.id} has proximal point: {p}, distal: {d}"
                )
            # spherical segment
            if p.x == d.x and p.y == d.y and p.z == d.z and p.diameter == d.diameter:
                ax.scatter(
                    [p.x], [p.y], [p.z], color="red", marker="o", linewidth=p.diameter
                )
            else:
                ax.plot(
                    [p.x, d.x],
                    [p.y, d.y],
                    [p.z, d.z],
                    color="blue",
                    linewidth=(p.diameter + d.diameter) / 2,
                )

        limits = np.array([getattr(ax, f"get_{axis}lim")() for axis in "xyz"])
        ax.set_box_aspect(np.ptp(limits, axis=1))

        if save_to_file:
            logger.info(
                "Saving image to %s of plot: %s"
                % (os.path.abspath(save_to_file), title)
            )
            abs_file = os.path.abspath(save_to_file)
            plt.savefig(abs_file, dpi=200)

        if not nogui:
            plt.show()


def plot_interactive_3D_matplotlib(
    nml_file: str,
    verbose: bool = False,
    nogui: bool = False,
    save_to_file: typing.Optional[str] = None,
):
    """Plot NeuroML2 cell morphology interactively using matplotlib surfaces.

    :param nml_file: path to NeuroML cell file
    :type nml_file: str
    :param verbose: show extra information (default: False)
    :type verbose: bool
    :param nogui: do not show matplotlib GUI (default: false)
    :type nogui: bool
    :param save_to_file: optional filename to save generated morphology to
    :type save_to_file: str
    """
    nml_model = read_neuroml2_file(nml_file)

    fig = plt.figure()
    ax = fig.add_subplot(projection="3d")
    ax.set_xlabel("extent (um)")
    ax.set_ylabel("extent (um)")
    ax.set_zlabel("extent (um)")

    for cell in nml_model.cells:
        title = f"3D plot of {cell.id} from {nml_file}"

        logger.info(
            f"Plotting morphology of cell {cell.id} from {nml_file} with {len(cell.morphology.segments)} segments"
        )
        for seg in cell.morphology.segments:
            p = cell.get_actual_proximal(seg.id)
            d = seg.distal
            if verbose:
                print(
                    f"\nSegment {seg.name}, id: {seg.id} has proximal point: {p}, distal: {d}"
                )
            X = Y = Z = X_cap = Y_cap = Z_cap = None
            # spherical segment
            if p.x == d.x and p.y == d.y and p.z == d.z and p.diameter == d.diameter:
                X, Y, Z = get_sphere_surface(
                    p.x, p.y, p.z, p.diameter / 2, resolution=8
                )
                ax.plot_surface(X=X, Y=Y, Z=Z, color="red")
            else:
                # for a cylinder, only use two points on axis
                if p.diameter == d.diameter:
                    resolution = 2
                else:
                    resolution = 3

                X, Y, Z, X_cap, Y_cap, Z_cap = get_frustrum_surface(
                    p.x,
                    p.y,
                    p.z,
                    p.diameter / 2,
                    d.x,
                    d.y,
                    d.z,
                    d.diameter / 2,
                    resolution=resolution,
                )
                ax.plot_surface(X=X, Y=Y, Z=Z, color="blue")

            if X_cap is not None and Y_cap is not None and Z_cap is not None:
                ax.plot_surface(X=X_cap, Y=Y_cap, Z=Z_cap, color="blue")

        limits = np.array([getattr(ax, f"get_{axis}lim")() for axis in "xyz"])
        ax.set_box_aspect(np.ptp(limits, axis=1))

        if save_to_file:
            logger.info(
                "Saving image to %s of plot: %s"
                % (os.path.abspath(save_to_file), title)
            )
            abs_file = os.path.abspath(save_to_file)
            plt.savefig(abs_file, dpi=200)

        if not nogui:
            plt.show()


def plot_interactive_3D_web(
    nml_file: str,
    verbose: bool = False,
    nogui: bool = False,
    save_to_file: typing.Optional[str] = None,
):
    """Plot NeuroML2 cell morphology interactively in your web browser using Plot.ly
    This function works well for cell morphologies that contain < 1000 segments.

    Please note that the interactive plot uses Plotly, which uses WebGL. So,
    you need to use a WebGL enabled browser, and performance here may be
    hardware dependent.

    https://plotly.com/python/webgl-vs-svg/
    https://en.wikipedia.org/wiki/WebGL

    :param nml_file: path to NeuroML cell file
    :type nml_file: str
    :param verbose: show extra information (default: False)
    :type verbose: bool
    :param nogui: do not show matplotlib GUI (default: false)
    :type nogui: bool
    :param save_to_file: optional filename to save generated morphology to
    :type save_to_file: str
    """
    nml_model = read_neuroml2_file(nml_file)

    fig = go.Figure()
    for cell in nml_model.cells:
        title = f"3D plot of {cell.id} from {nml_file}"

        logger.info(
            f"Plotting morphology of cell {cell.id} from {nml_file} with {len(cell.morphology.segments)} segments"
        )
        for seg in cell.morphology.segments:
            p = cell.get_actual_proximal(seg.id)
            d = seg.distal
            if verbose:
                print(
                    f"\nSegment {seg.name}, id: {seg.id} has proximal point: {p}, distal: {d}"
                )
            X = Y = Z = X_cap = Y_cap = Z_cap = None
            # spherical segment
            if p.x == d.x and p.y == d.y and p.z == d.z and p.diameter == d.diameter:
                X, Y, Z = get_sphere_surface(
                    p.x, p.y, p.z, p.diameter / 2, resolution=8
                )
                fig.add_trace(
                    go.Surface(
                        x=X,
                        y=Y,
                        z=Z,
                        surfacecolor=(len(Z) * ["red"]),
                        contours=dict(
                            x=None,
                            y=None,
                            z=None,
                        ),
                        hoverinfo="skip",
                        showscale=False,
                    )
                )
            else:
                # for a cylinder, only use two points on axis
                if p.diameter == d.diameter:
                    resolution = 2
                else:
                    resolution = 3

                X, Y, Z, X_cap, Y_cap, Z_cap = get_frustrum_surface(
                    p.x,
                    p.y,
                    p.z,
                    p.diameter / 2,
                    d.x,
                    d.y,
                    d.z,
                    d.diameter / 2,
                    resolution=resolution,
                )
                fig.add_trace(
                    go.Surface(
                        x=X,
                        y=Y,
                        z=Z,
                        surfacecolor=(len(X) * len(Y) * ["blue"]),
                        contours=dict(
                            x=None,
                            y=None,
                            z=None,
                        ),
                        hoverinfo="skip",
                        showscale=False,
                    )
                )

            if X_cap is not None and Y_cap is not None and Z_cap is not None:
                fig.add_trace(
                    go.Surface(
                        x=X_cap,
                        y=Y_cap,
                        z=Z_cap,
                        surfacecolor=(len(X_cap) * len(Y_cap) * ["blue"]),
                        contours=dict(
                            x=None,
                            y=None,
                            z=None,
                        ),
                        hoverinfo="skip",
                        showscale=False,
                    )
                )

        fig.update_layout(
            title={"text": title},
            hovermode=False,
            plot_bgcolor="white",
            scene=dict(
                aspectmode="data",
                aspectratio=dict(
                    x=1.0,
                    y=1.0,
                    z=1.0,
                ),
                xaxis=dict(
                    backgroundcolor="white",
                    showbackground=False,
                    showgrid=False,
                    showspikes=False,
                    title=dict(text="extent (um)"),
                ),
                yaxis=dict(
                    backgroundcolor="white",
                    showbackground=False,
                    showgrid=False,
                    showspikes=False,
                    title=dict(text="extent (um)"),
                ),
                zaxis=dict(
                    backgroundcolor="white",
                    showbackground=False,
                    showgrid=False,
                    showspikes=False,
                    title=dict(text="extent (um)"),
                ),
            ),
        )
        if not nogui:
            fig.show()
        if save_to_file:
            logger.info(
                "Saving image to %s of plot: %s"
                % (os.path.abspath(save_to_file), title)
            )
            fig.write_image(save_to_file, scale=2, width=1024, height=768)
            logger.info("Saved image to %s of plot: %s" % (save_to_file, title))


def plot_interactive_3D_web_naive(
    nml_file: str,
    verbose: bool = False,
    nogui: bool = False,
    min_width: float = 0.2,
    save_to_file: typing.Optional[str] = None,
):
    """Plot NeuroML2 cell morphology interactively in your web browser using
    Plot.ly using lines.

    This is a more performant version of `plot_interactive_3D_web` that is able
    to plot more complex cell morphologies. Similar to the
    `plot_interactive_3D_matplotlib_naive` function, this uses lines instead of
    surfaces to represent segments.

    Please note that the interactive plot uses Plotly, which uses WebGL. So,
    you need to use a WebGL enabled browser, and performance here may be
    hardware dependent.

    https://plotly.com/python/webgl-vs-svg/
    https://en.wikipedia.org/wiki/WebGL

    :param nml_file: path to NeuroML cell file
    :type nml_file: str
    :param verbose: show extra information (default: False)
    :type verbose: bool
    :param nogui: do not show matplotlib GUI (default: false)
    :type nogui: bool
    :param save_to_file: optional filename to save generated morphology to
    :type save_to_file: str
    """
    nml_model = read_neuroml2_file(nml_file)
    fig = go.Figure()
    for cell in nml_model.cells:
        title = f"3D plot of {cell.id} from {nml_file}"

        for seg in cell.morphology.segments:
            p = cell.get_actual_proximal(seg.id)
            d = seg.distal
            if verbose:
                print(
                    f"\nSegment {seg.name}, id: {seg.id} has proximal point: {p}, distal: {d}"
                )
            width = max(p.diameter, d.diameter)
            if width < min_width:
                width = min_width
            fig.add_trace(
                go.Scatter3d(
                    x=[p.x, d.x],
                    y=[p.y, d.y],
                    z=[p.z, d.z],
                    name=None,
                    marker={"size": 2, "color": "blue"},
                    line={"width": width, "color": "blue"},
                    mode="lines",
                    showlegend=False,
                    hoverinfo="skip",
                )
            )

        fig.update_layout(
            title={"text": title},
            hovermode=False,
            plot_bgcolor="white",
            scene=dict(
                xaxis=dict(
                    backgroundcolor="white",
                    showbackground=False,
                    showgrid=False,
                    showspikes=False,
                    title=dict(text="extent (um)"),
                ),
                yaxis=dict(
                    backgroundcolor="white",
                    showbackground=False,
                    showgrid=False,
                    showspikes=False,
                    title=dict(text="extent (um)"),
                ),
                zaxis=dict(
                    backgroundcolor="white",
                    showbackground=False,
                    showgrid=False,
                    showspikes=False,
                    title=dict(text="extent (um)"),
                ),
            ),
        )
        if not nogui:
            fig.show()
        if save_to_file:
            logger.info(
                "Saving image to %s of plot: %s"
                % (os.path.abspath(save_to_file), title)
            )
            fig.write_image(save_to_file, scale=2, width=1024, height=768)
            logger.info("Saved image to %s of plot: %s" % (save_to_file, title))


if __name__ == "__main__":
    main()