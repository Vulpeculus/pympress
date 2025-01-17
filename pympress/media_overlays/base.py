# -*- coding: utf-8 -*-
#
#       media_overlays/base.py
#
#       Copyright 2015 Cimbali <me@cimba.li>
#
#       Vaguely inspired from:
#       gtk example/widget for VLC Python bindings
#       Copyright (C) 2009-2010 the VideoLAN team
#
#       This program is free software; you can redistribute it and/or modify
#       it under the terms of the GNU General Public License as published by
#       the Free Software Foundation; either version 2 of the License, or
#       (at your option) any later version.
#
#       This program is distributed in the hope that it will be useful,
#       but WITHOUT ANY WARRANTY; without even the implied warranty of
#       MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#       GNU General Public License for more details.
#
#       You should have received a copy of the GNU General Public License
#       along with this program; if not, write to the Free Software
#       Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston MA 02110-1301, USA.
#

"""
:mod:`pympress.media_overlays.base` -- widget to play videos with a backend like VLC
------------------------------------------------------------------------------------
"""

from __future__ import print_function, unicode_literals

import logging
logger = logging.getLogger(__name__)

import gi
import cairo
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk, GObject, GLib, GdkPixbuf

try:
    gi.require_version('GdkX11', '3.0')
    from gi.repository import GdkX11
except:
    pass

import ctypes

from pympress.util import IS_POSIX, IS_MAC_OS, IS_WINDOWS
from pympress import builder


def get_window_handle(window):
    """ Uses ctypes to call gdk_win32_window_get_handle which is not available
    in python gobject introspection porting (yet ?)
    Solution from http://stackoverflow.com/a/27236258/1387346

    Args:
        window (:class:`~Gdk.Window`): The window for which we want to get the handle

    Returns:
        The handle to the win32 window
    """
    # get the c gpointer of the gdk window
    ctypes.pythonapi.PyCapsule_GetPointer.restype = ctypes.c_void_p
    ctypes.pythonapi.PyCapsule_GetPointer.argtypes = [ctypes.py_object]
    drawingarea_gpointer = ctypes.pythonapi.PyCapsule_GetPointer(window.__gpointer__, None)
    # get the win32 handle
    gdkdll = ctypes.CDLL('libgdk-3-0.dll')
    return gdkdll.gdk_win32_window_get_handle(drawingarea_gpointer)


class VideoOverlay(builder.Builder):
    """ Simple Video widget.

    Args:
        container (:class:`~Gtk.Overlay`): The container with the slide, at the top of which we add the movie area
        show_controls (`bool`): whether to display controls on the video player
        page_type (:class:`~pympress.document.PdfPage`): the part of the page to display
        relative_margins (:class:`~Poppler.Rectangle`): the margins defining the position of the video in the frame.
    """
    #: :class:`~Gtk.Overlay` that is the parent of the VideoOverlay widget.
    parent = None
    #: :class:`~Gtk.VBox` that contains all the elements to be overlayed.
    media_overlay = None
    #: A :class:`~Gtk.HBox` containing a toolbar with buttons and :attr:`~progress` the progress bar
    toolbar = None
    #: :class:`~Gtk.Scale` that is the progress bar in the controls toolbar - if we have one.
    progress = None
    #: :class:`~Gtk.DrawingArea` where the media is rendered.
    movie_zone = None
    #: `tuple` containing the left/top/right/bottom space around the drawing area in the PDF page
    relative_page_margins = None
    #: `tuple` containing the left/top/right/bottom space around the drawing area in the visible slide
    relative_margins = None
    #: `bool` that tracks whether we should play automatically
    autoplay = False

    #: callback, to be connected to :meth:`~pympress.extras.Media.play`, curryfied with the correct media_id
    play = None
    #: callback, to be connected to :meth:`~pympress.extras.Media.hide`, curryfied with the correct media_id
    hide = None
    #: callback, to be connected to :meth:`~pympress.extras.Media.play_pause`, curryfied with the correct media_id
    play_pause = None
    #: callback, to be connected to :meth:`~pympress.extras.Media.set_time`, curryfied with the correct media_id
    set_time = None

    #: `bool` that tracks whether the user is dragging the position
    dragging_position = False
    #: `bool` that tracks whether the playback was paused when the user started dragging the position
    dragging_paused = False
    #: Format of the video time, defaults to m:ss, changed to m:ss / m:ss when the max time is known
    time_format = '{:01}:{:02}'
    #: `float` holding the max time in s
    maxval = 1

    def __init__(self, container, show_controls, relative_margins, page_type, callback_getter):
        super(VideoOverlay, self).__init__()

        self.parent = container
        self.relative_page_margins = tuple(getattr(relative_margins, v) for v in ('x1', 'y2', 'x2', 'y1'))
        self.update_margins_for_page(page_type)

        self.load_ui('media_overlay')
        self.toolbar.set_visible(show_controls)

        self.play = callback_getter('play')
        self.hide = callback_getter('hide')
        self.play_pause = callback_getter('play_pause')
        self.set_time = callback_getter('set_time')
        self.connect_signals(self)


    def handle_embed(self, mapped_widget):
        """ Handler to embed the video player in the correct window, connected to the :attr:`~.Gtk.Widget.signals.map` signal
        """
        return False


    def format_millis(self, sc, prog):
        """ Callback to format the current timestamp (in milliseconds) as minutes:seconds

        Args:
            sc (:class:`~Gtk.Scale`): The scale whose position we are formatting
            prog (`float`): The position of the :class:`~Gtk.Scale`, i.e. the number of seconds elapsed
        """
        return self.time_format.format(*divmod(int(round(prog)), 60))


    def update_range(self, max_time):
        """ Update the toolbar slider size.

        Args:
            max_time (`float`): The maximum time in this video in s
        """
        self.maxval = max_time
        self.progress.set_range(0, self.maxval)
        self.progress.set_increments(min(5., self.maxval / 10.), min(60., self.maxval / 10.))
        sec = round(self.maxval) if self.maxval > .5 else 1.
        self.time_format = '{{:01}}:{{:02}} / {:01}:{:02}'.format(*divmod(int(sec), 60))


    def update_progress(self, time):
        """ Update the toolbar slider to the current time.

        Args:
            time (`float`): The time in this video in s
        """
        self.progress.set_value(time)


    def progress_moved(self, rng, sc, val):
        """ Callback to update the position of the video when the user moved the progress bar.

        Args:
            rng (:class:`~Gtk.Range`): The range corresponding to the scale whose position we are formatting
            sc (:class:`~Gtk.Scale`): The scale whose position we are updating
            val (`float`): The position of the :class:`~Gtk.Scale`, which is the number of seconds elapsed in the video
        """
        return self.set_time(val)


    def update_margins_for_page(self, page_type):
        """
        Arguments:
            page_type (:class:`~pympress.document.PdfPage`): the part of the page to display
        """
        self.relative_margins = page_type.to_screen(*self.relative_page_margins)


    def resize(self):
        """ Adjust the position and size of the media overlay.
        """
        if not self.is_shown():
            return

        pw, ph = self.parent.get_allocated_width(), self.parent.get_allocated_height()
        self.media_overlay.props.margin_left   = pw * self.relative_margins[0]
        self.media_overlay.props.margin_right  = pw * self.relative_margins[2]
        self.media_overlay.props.margin_bottom = ph * self.relative_margins[3]
        self.media_overlay.props.margin_top    = ph * self.relative_margins[1]


    def is_shown(self):
        """ Returns whether the media overlay is currently added to the overlays, or hidden.

        Returns:
            `bool`: `True` iff the overlay is currently displayed.
        """
        return self.media_overlay.get_parent() is not None


    def is_playing(self):
        """ Returns whether the media is currently playing (and not paused).

        Returns:
            `bool`: `True` iff the media is playing.
        """
        raise NotImplementedError


    def do_stop(self):
        """ Stops playing in the backend player.
        """
        raise NotImplementedError


    def set_file(self, filepath):
        """ Sets the media file to be played by the widget.

        Args:
            filepath (`str`): The path to the media file path
        """
        raise NotImplementedError


    def show(self):
        """ Bring the widget to the top of the overlays if necessary.
        """
        if min(self.relative_margins) < 0:
            logger.warning('Not showing media with (some) negative margin(s): LTRB = {}'.format(self.relative_margins))
            return

        if not self.media_overlay.get_parent():
            self.parent.add_overlay(self.media_overlay)
            self.parent.reorder_overlay(self.media_overlay, 2)
            self.resize()
            self.parent.queue_draw()
        self.media_overlay.show()


    def do_hide(self):
        """ Remove widget from overlays. Needs to be callded via GLib.idle_add

        Returns:
            `bool`: `True` iff this function should be run again (:func:`~GLib.idle_add` convention)
        """
        self.do_stop()
        self.media_overlay.hide()

        if self.media_overlay.get_parent():
            self.parent.remove(self.media_overlay)
        return False


    def do_play(self):
        """ Start playing the media file.
        Should run on the main thread to ensure we avoid vlc plugins' reentrency problems.

        Returns:
            `bool`: `True` iff this function should be run again (:meth:`~GLib.idle_add` convention)
        """
        raise NotImplementedError


    def do_play_pause(self):
        """ Toggle pause mode of the media.
        Should run on the main thread to ensure we avoid vlc plugins' reentrency problems.

        Returns:
            `bool`: `True` iff this function should be run again (:meth:`~GLib.idle_add` convention)
        """
        raise NotImplementedError


    def do_set_time(self, t):
        """ Set the player at time t.
        Should run on the main thread to ensure we avoid vlc plugins' reentrency problems.

        Args:
            t (`float`): the timestamp, in s

        Returns:
            `bool`: `True` iff this function should be run again (:meth:`~GLib.idle_add` convention)
        """
        raise NotImplementedError
