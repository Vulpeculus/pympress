# -*- coding: utf-8 -*-
#
#       pointer.py
#
#       Copyright 2017 Cimbali <me@cimba.li>
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
#       Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston,
#       MA 02110-1301, USA.

"""
:mod:`pympress.pointer` -- Manage when and where to draw a software-emulated laser pointer on screen
----------------------------------------------------------------------------------------------------
"""

from __future__ import print_function, unicode_literals

import logging
logger = logging.getLogger(__name__)

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gdk, GdkPixbuf

from pympress import util, extras


#: Pointer enabled but hidden, will be drawn on ctrl + click
POINTER_HIDE = 0
#: Draw the pointer on the current slide
POINTER_SHOW = 1

#: Pointer switched on contineously
POINTERMODE_CONTINEOUS = 1
#: Pointer switched on only manual
POINTERMODE_MANUAL = 0
#: Pointer never switched on
POINTERMODE_DISABLED = -1



class Pointer(object):
    #: :class:`~GdkPixbuf.Pixbuf` to read XML descriptions of GUIs and load them.
    pointer = GdkPixbuf.Pixbuf()
    #: `(float, float)` of position relative to slide, where the pointer should appear
    pointer_pos = (.5, .5)
    #: `bool` indicating whether we should show the pointer
    show_pointer = POINTER_HIDE
    #: `bool` indicating the pointer mode 
    pointer_mode = POINTERMODE_MANUAL
    #: A reference to the UI's :class:`~pympress.config.Config`, to update the pointer preference
    config = None
    #: :class:`~Gtk.Box` in the Presenter window, used to reliably set cursors.
    p_da_cur = None


    #: callback, to be connected to :func:`~pympress.ui.UI.redraw_current_slide`
    redraw_current_slide = lambda: None

    def __init__(self, config, builder):
        """ Setup the pointer management, and load the default pointer

        Args:
            config (:class:`~pympress.config.Config`): A config object containing preferences
            builder (:class:`~pympress.builder.Builder`): A builder from which to load widgets
        """
        super(Pointer, self).__init__()
        self.config = config

        builder.load_widgets(self)

        self.redraw_current_slide = builder.get_callback_handler('redraw_current_slide')

        default_mode = config.get('presenter', 'pointer_mode')
        self.activate_pointermode(default_mode)

        for radio_name in ['pointermode_continous', 'pointermode_manual', 'pointermode_none']:
            radio = builder.get_object(radio_name)
            radio.set_name(radio_name)

            radio.set_active(radio_name == 'pointermode_' + default_mode)

        default_color = 'pointer_' + config.get('presenter', 'pointer')
        self.load_pointer(default_color)

        for radio_name in ['pointer_red', 'pointer_blue', 'pointer_green']:
            radio = builder.get_object(radio_name)
            radio.set_name(radio_name)

            radio.set_active(radio_name == default_color)


    def load_pointer(self, name):
        """ Perform the change of pointer using its color name

        Args:
            name (`str`): Name of the pointer to load
        """
        if name in ['pointer_red', 'pointer_green', 'pointer_blue']:
            self.pointer = GdkPixbuf.Pixbuf.new_from_file(util.get_icon_path(name + '.png'))
        else:
            raise ValueError('Wrong color name')


    def change_pointer(self, widget):
        """ Callback for a radio item selection as pointer color

        Args:
            widget (:class:`~Gtk.RadioMenuItem`): the selected radio item in the pointer type selection menu
        """
        if widget.get_active():
            assert(widget.get_name().startswith('pointer_'))
            self.load_pointer(widget.get_name())
            self.config.set('presenter', 'pointer', widget.get_name()[len('pointer_'):])

    def activate_pointermode(self, mode=None):
        """ Activate the pointer as given by mode

        Args:
            mode (`str`): Name of the mode to activate (contineous|manual|disabled)
        """
        # Set internal variables, unless called without mode (from ui, after windows have been mapped)
        if mode == 'continous':
            self.show_pointer = POINTER_SHOW
            self.pointer_mode = POINTERMODE_CONTINEOUS
        elif mode == 'manual':
            self.show_pointer = POINTER_HIDE
            self.pointer_mode = POINTERMODE_MANUAL
        elif mode == 'none':
            self.show_pointer = POINTER_HIDE
            self.pointer_mode = POINTERMODE_DISABLED

        # Set mouse pointer on/off, if windows are already mapped
        if self.p_da_cur.get_window():
            if self.pointer_mode == POINTERMODE_CONTINEOUS:
                extras.Cursor.set_cursor(self.p_da_cur, 'invisible')
            else:
                extras.Cursor.set_cursor(self.p_da_cur, 'parent')

            self.redraw_current_slide()


    def change_pointermode(self, widget):
        """ Callback for a radio item selection as pointer mode (continous, manual, disabled)

        Args:
            widget (:class:`~Gtk.RadioMenuItem`): the selected radio item in the pointer type selection menu
        """
        if widget.get_active():
            assert(widget.get_name().startswith('pointermode_'))
            mode = widget.get_name()[len('pointermode_'):]
            self.config.set('presenter', 'pointer_mode', mode)
            self.activate_pointermode(mode)


    def render_pointer(self, cairo_context, ww, wh):
        """ Draw the laser pointer on screen

        Args:
            cairo_context (:class:`~cairo.Context`): The canvas on which to render the pointer
            ww (`int`): The widget width
            wh (`int`): The widget height
        """
        if self.show_pointer == POINTER_SHOW:
            x = ww * self.pointer_pos[0] - self.pointer.get_width() / 2
            y = wh * self.pointer_pos[1] - self.pointer.get_height() / 2
            Gdk.cairo_set_source_pixbuf(cairo_context, self.pointer, x, y)
            cairo_context.paint()


    def track_pointer(self, widget, event):
        """ Move the laser pointer at the mouse location.

        Args:
            widget (:class:`~Gtk.Widget`):  the widget which has received the event.
            event (:class:`~Gdk.Event`):  the GTK event.

        Returns:
            `bool`: whether the event was consumed
        """
        if self.show_pointer == POINTER_SHOW:
            ww, wh = widget.get_allocated_width(), widget.get_allocated_height()
            ex, ey = event.get_coords()
            self.pointer_pos = (ex / ww, ey / wh)
            self.redraw_current_slide()
            return True

        else:
            return False


    def toggle_pointer(self, widget, event):
        """ Track events defining when the laser is pointing.

        Args:
            widget (:class:`~Gtk.Widget`):  the widget which has received the event.
            event (:class:`~Gdk.Event`):  the GTK event.

        Returns:
            `bool`: whether the event was consumed
        """
        if self.pointer_mode == POINTERMODE_DISABLED:
            return False

        if self.pointer_mode == POINTERMODE_CONTINEOUS:
            return False

        ctrl_pressed = event.get_state() & Gdk.ModifierType.CONTROL_MASK

        if ctrl_pressed and event.type == Gdk.EventType.BUTTON_PRESS:
            self.show_pointer = POINTER_SHOW
            extras.Cursor.set_cursor(widget, 'invisible')

            # Immediately place & draw the pointer
            return self.track_pointer(widget, event)

        elif self.show_pointer == POINTER_SHOW and event.type == Gdk.EventType.BUTTON_RELEASE:
            self.show_pointer = POINTER_HIDE
            extras.Cursor.set_cursor(widget, 'parent')
            self.redraw_current_slide()
            return True

        else:
            return False


