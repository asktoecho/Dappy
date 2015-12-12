#    This file is part of Dappy - Draw And Paint in Python
#    Copyright (C) 2015 Julian Stirling
#
#    Dappy was forked from Painthon, listed on Google code as GPL v2,
#    copyright holder unknown.
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>

import cairo
import gtk
import gobject
import math
from ctypes import create_string_buffer
import tools
from colors import RGBAColor
from dappygui import senstivity_data

class undoBuffer:
    n_buf = 5
    cur_buf = 0
    n_buf_full = 0
    redos_allowed = 0
    Buffer = None
    width = None
    height = None

    def __init__(self):
        self.Buffer = [None for i in range(self.n_buf+1)]
        self.width = [0 for i in range(self.n_buf+1)]
        self.height = [0 for i in range(self.n_buf+1)]

    def next_buf(self):
        return (self.cur_buf+1)%(self.n_buf+1)

    def prev_buf(self):
        return (self.cur_buf-1)%(self.n_buf+1)

class Canvas(gtk.DrawingArea):
    DEFAULT_CURSOR = gtk.gdk.Cursor(gtk.gdk.ARROW)
    active_tool = None
    picker_col = None
    bg_init=None
    bg_col = None
    UNDO_BUFFER = undoBuffer()
    select_active = None
    modified = None
    fig_fill_type = None

    def __init__(self):
        # Initializing gtk.DrawingArea superclass
        super(Canvas, self).__init__()

        # Registering events
        self.add_events(gtk.gdk.BUTTON_PRESS_MASK | gtk.gdk.BUTTON_RELEASE_MASK | gtk.gdk.BUTTON1_MOTION_MASK | gtk.gdk.DRAG_MOTION | gtk.gdk.POINTER_MOTION_MASK)
        self.connect("button-press-event", self.button_pressed)
        self.connect("button-release-event", self.button_released)
        self.connect("motion-notify-event", self.move_event)
        self.connect("expose-event", self.expose)
        self.connect("motion-notify-event", self.motion_event)

        self.set_size(550, 412)
        self.ALPHA_PATTERN = cairo.SurfacePattern(cairo.ImageSurface.create_from_png("GUI/alpha-pattern.png"))
        self.ALPHA_PATTERN.set_extend(cairo.EXTEND_REPEAT)

        self.bg_init=0
        self.bg_col = (1, 1, 1, 1)

        self.figure_linewidth=0
        self.figure_corner_radius=0
        self.airbrush_width=0

        self.set_selection(False)
        self.select_xp = None
        self.select_yp = None

        self.fig_fill_type = 0

        self.modified = False

        # Basic tools
        self.DUMMY_TOOL = tools.Tool(self)
        self.active_tool = self.DUMMY_TOOL

        # Surface is the image in the canvas
        self.surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, self.width, self.height)
        #overlay is for selection boxes - etc
        self.overlay = cairo.ImageSurface(cairo.FORMAT_ARGB32, self.width, self.height)

        #clipboard
        self.clipboard = gtk.clipboard_get(selection="CLIPBOARD")


    def set_size(self, width, height): #Not called by fancycanvas objects!
        self.width = max(width, 1)
        self.height = max(height, 1)
        self.set_size_request(self.width, self.height)

    def get_width(self):
        return self.width


    def get_height(self):
        return self.height


    def set_active_tool(self, tool):
        self.active_tool = tool


    def button_pressed(self, widget, event):
        if event.type == gtk.gdk.BUTTON_PRESS:
            self.active_tool.begin(event.x, event.y,event.button)
            self.swap_buffers()

    def button_released(self, widget, event):
        self.active_tool.end(event.x, event.y)
        self.swap_buffers()
        self.active_tool.commit()
        if self.active_tool.name == "ColorPicker":
            col = self.active_tool.col
            self.picker_col =  RGBAColor(col[2], col[1], col[0], col[3])
            self.emit("color_pick_event", event)

    #always runs when mouse moves
    def move_event(self, widget, event):
        self.active_tool.move(event.x, event.y)
        if self.active_tool.name == "ColorPicker" and  self.active_tool.mode == self.active_tool.DRAWING:
            col = self.active_tool.col
            self.picker_col =  RGBAColor(col[2], col[1], col[0], col[3])
            self.emit("color_pick_event", event)
        else:
            self.swap_buffers()

    #captured by fancy canvas and only run if not over scaling point.
    def motion_event(self, widget, event):
        self.active_tool.select()
        if event.x > self.width or event.y > self.height:
            self.window.set_cursor(self.DEFAULT_CURSOR)


    def swap_buffers(self):
        rect = gtk.gdk.Rectangle(0, 0, self.width, self.height)
        self.window.invalidate_rect(rect, True) #invalidating the rectangle forces gtk to run expose.

    def expose(self, widget, event): # Run when buffers are swapped: updates screen.
        #temporary surface size of canvas
        tmp_surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, self.width, self.height)
        context = cairo.Context(tmp_surf)
        #draw to this temporary surface
        self.draw(context)
        if self.active_tool.name == "AirBrush" and  self.active_tool.mode == self.active_tool.DRAWING:
            self.surface = tmp_surf
        #get widget window as context
        wincontext = widget.window.cairo_create()
        #clip to image size
        wincontext.rectangle(0, 0, self.width, self.height)
        wincontext.clip()
        #paint alpha pattern over whole clipped region
        wincontext.set_source(self.ALPHA_PATTERN)
        wincontext.paint()
        #paint
        wincontext.set_source_surface(tmp_surf)
        wincontext.paint()
        #overlay
        wincontext.set_source_surface(self.overlay)
        wincontext.paint()

    def print_tool(self):
        self.clear_overlay()
        #temporary surface size of canvas
        tmp_surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, self.width, self.height)
        context = cairo.Context(tmp_surf)
        #draw to temporary surface
        self.draw(context)
        self.surface = tmp_surf #surface now swapped with updated surface

    def draw(self, context):
        # Drawing the background
        self.__draw_background(context)
        #Draw the current surface over the background
        context.set_source_surface(self.surface)
        context.paint()
        #Draw any active tool if applicable.
        if self.active_tool.Draw2Overlay:
            ov_context = cairo.Context(self.overlay)
            self.active_tool.draw(ov_context)
        else:
            self.active_tool.draw(context)

    def __draw_background(self, context):
        #if the background has never been initialsed (first print) then
        #fill whole canvas, else fill new regions
        if self.bg_init==0:
            context.rectangle(0, 0, self.width, self.height)
            self.bg_init=1
        else:
            context.rectangle(self.surface.get_width(), 0, self.width-self.surface.get_width(), self.height)
            context.rectangle(0, self.surface.get_height(), self.width, self.height-self.surface.get_height())
        context.set_source_rgba(self.bg_col[0], self.bg_col[1], self.bg_col[2], self.bg_col[3])
        context.fill()

    def clear_overlay(self):
        #temporary surface size of canvase
        tmp_surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, self.width, self.height)
        context= cairo.Context(tmp_surf)
        #paint surface transparent
        context.rectangle(0, 0, self.width, self.height)
        context.set_source_rgba(0, 0, 0, 0)
        context.fill()
        #set as overlay
        self.overlay = tmp_surf
        self.set_selection(False)

    def set_selection(self,value):
        if self.select_active != value:
            self.select_active = value
            self.emit("change_sensitivty", senstivity_data('crop',value))

    def get_image(self):
        return self.surface


    def set_image(self, surface):
        self.surface = surface
        self.set_size(surface.get_width(), surface.get_height())


    def get_color(self):
        return self.picker_col

    def undo(self):
        if self.UNDO_BUFFER.n_buf_full>0:
            self.modified=True
            self.update_undo_buffer(0)
            buf = self.UNDO_BUFFER.prev_buf()
            data = self.surface.get_data()
            w = self.surface.get_width()
            h = self.surface.get_height()
            bw = self.UNDO_BUFFER.width[buf]
            bh = self.UNDO_BUFFER.height[buf]
            if bh!=h | bw!=w:
                self.set_size(bw,bh)
                self.print_tool()
                data = self.surface.get_data()
            data[:] = self.UNDO_BUFFER.Buffer[buf][:]
            self.UNDO_BUFFER.n_buf_full -=1
            if self.UNDO_BUFFER.redos_allowed<self.UNDO_BUFFER.n_buf:
                self.UNDO_BUFFER.redos_allowed += 1
            self.UNDO_BUFFER.cur_buf = buf
            self.swap_buffers()
            self.emit("change_sensitivty", senstivity_data('redo',True))
            if self.UNDO_BUFFER.n_buf_full==0:
                self.emit("change_sensitivty", senstivity_data('undo',False))


    def redo(self):
        if self.UNDO_BUFFER.redos_allowed>0:
            self.modified=True
            buf = self.UNDO_BUFFER.next_buf()
            data = self.surface.get_data()
            w = self.surface.get_width()
            h = self.surface.get_height()
            bw = self.UNDO_BUFFER.width[buf]
            bh = self.UNDO_BUFFER.height[buf]
            if bh!=h | bw!=w:
                self.set_size(bw,bh)
                self.print_tool()
                data = self.surface.get_data()
            data[:] = self.UNDO_BUFFER.Buffer[buf][:]
            self.UNDO_BUFFER.redos_allowed -=1
            self.UNDO_BUFFER.n_buf_full +=1
            self.UNDO_BUFFER.cur_buf = buf
            self.swap_buffers()
            self.emit("change_sensitivty", senstivity_data('undo',True))
            if self.UNDO_BUFFER.redos_allowed==0:
                self.emit("change_sensitivty", senstivity_data('redo',False))


    def update_undo_buffer(self,iterate):
        self.modified=True
        w = self.surface.get_width()
        h = self.surface.get_height()
        s = self.surface.get_stride()
        data = self.surface.get_data()
        buf = self.UNDO_BUFFER.cur_buf
        self.UNDO_BUFFER.Buffer[buf] = create_string_buffer(s*h)
        self.UNDO_BUFFER.Buffer[buf][:] = data[:]
        self.UNDO_BUFFER.width[buf] = w
        self.UNDO_BUFFER.height[buf] = h
        if iterate==1:
            self.emit("change_sensitivty", senstivity_data('undo',True))
            self.emit("change_sensitivty", senstivity_data('redo',False))
            self.UNDO_BUFFER.redos_allowed = 0
            if self.UNDO_BUFFER.n_buf_full<self.UNDO_BUFFER.n_buf:
                self.UNDO_BUFFER.n_buf_full += 1
            self.UNDO_BUFFER.cur_buf = self.UNDO_BUFFER.next_buf()

    def clear_undo_buffer(self):
        self.emit("change_sensitivty", senstivity_data('undo',False))
        self.emit("change_sensitivty", senstivity_data('redo',False))
        self.UNDO_BUFFER.cur_buf = 0
        self.UNDO_BUFFER.n_buf_full = 0
        self.UNDO_BUFFER.redos_allowed = 0

    def copy(self,cut):
        data = self.surface.get_data()
        t_data=list(data)
        t_data[::4] = data[2::4]
        t_data[2::4] = data[::4]
        s = self.surface.get_stride()
        w = self.surface.get_width()
        h = self.surface.get_height()
        if self.select_active:
            xp= [min(max(0,x),w) for x in self.select_xp]
            yp= [min(max(0,y),h) for y in self.select_yp]
            c_w= int(max(xp)-min(xp))
            c_h= int(max(yp)-min(yp))
            if c_h>0 and c_w>0:
                c_s = c_w*4
                c_data=[t_data[0]]*(c_h*c_s)
                c_y = int(min(yp))
                c_x = int(min(xp))
                for n in range(c_h):
                    c_data[n*c_s:(n+1)*c_s] = t_data[(n+c_y)*s+c_x*4:(n+c_y)*s+c_x*4+c_s]
                c_data = ''.join(c_data)
                PixBuf =  gtk.gdk.pixbuf_new_from_data(c_data,gtk.gdk.COLORSPACE_RGB, True, 8, c_w,c_h,c_s)
                self.clipboard.set_image(PixBuf)
                if cut:
                    self.delete()
        else:
            t_data = ''.join(t_data)
            PixBuf =  gtk.gdk.pixbuf_new_from_data(t_data,gtk.gdk.COLORSPACE_RGB, True, 8, w,h,s)
            self.clipboard.set_image(PixBuf)
            if cut:
                self.delete()

    def delete(self):
        w = self.surface.get_width()
        h = self.surface.get_height()
        if self.select_active:
            xp= [min(max(0,x),w) for x in self.select_xp]
            yp= [min(max(0,y),h) for y in self.select_yp]
            c_w= int(max(xp)-min(xp))
            c_h= int(max(yp)-min(yp))
            if c_h>0 and c_w>0:
                c_y = int(min(yp))
                c_x = int(min(xp))
                self.update_undo_buffer(1)
                aux = cairo.ImageSurface(cairo.FORMAT_ARGB32, c_w, c_h)
                context  = cairo.Context(aux)
                context.rectangle(0, 0, self.width, self.height)
                context.set_source_rgba(self.bg_col[0], self.bg_col[1], self.bg_col[2], self.bg_col[3])
                context.fill()
                mask = cairo.ImageSurface(cairo.FORMAT_ARGB32, w, h)
                context  = cairo.Context(mask)
                context.rectangle(0, 0, self.width, self.height)
                context.set_source_rgba(1,1,1,0)
                context.fill()
                context.rectangle(c_x, c_y, c_w, c_h)
                context.set_source_rgba(1,1,1,1)
                context.fill()
                context = cairo.Context(self.surface)
                context.set_source_surface(aux, c_x, c_y)
                context.set_operator(cairo.OPERATOR_SOURCE)
                context.mask(cairo.SurfacePattern(mask))
                self.swap_buffers()
        else:
            data = self.surface.get_data()
            self.update_undo_buffer(1)
            context  = cairo.Context(self.surface)
            context.rectangle(0, 0, self.width, self.height)
            context.set_source_rgba(self.bg_col[0], self.bg_col[1], self.bg_col[2], self.bg_col[3])
            context.set_operator(cairo.OPERATOR_SOURCE)
            context.fill()
            #if the context is filled blank the pixels wont edit properly for bucket fill
            #The hacky solution is to copy the black pixels to a temporary array
            #Paint new pixels, and then copy the blank ones back in.
            if self.bg_col[3] == 0:
                t_data = data[:]
                context = cairo.Context(self.surface)
                context.paint()
                data[:] = t_data[:]
            self.swap_buffers()


    def paste(self):
        image = self.clipboard.wait_for_image()
        if image != None:
            self.update_undo_buffer(1)
            self.set_size(max(self.width,image.get_width()), max(self.height,image.get_height()))
            self.print_tool()
            aux = cairo.ImageSurface(cairo.FORMAT_ARGB32, image.get_width(), image.get_height())
            im_data = image.get_pixels()
            # the next two semingly useless lines give the surface real pixels to be edited.
            context = cairo.Context(aux)
            context.paint()
            #directly write to the pixels in aux
            data = aux.get_data()
            #pasted image has alpha channel
            if image.get_rowstride()==aux.get_stride():
                data[2::4] = im_data[0::4]#red
                data[0::4] = im_data[2::4] #blue
                data[1::4] = im_data[1::4] #green
                data[3::4] = im_data[3::4] #alpha
            else: #pasted data no alpha channel
                data[2::4] = im_data[0::3]#red
                data[0::4] = im_data[2::3] #blue
                data[1::4] = im_data[1::3] #green
            #use cairo to add the pasted image to the current image
            context = cairo.Context(self.surface)
            context.set_source_surface(aux, 0, 0)
            context.paint()
            self.swap_buffers()

    def crop(self):
        if self.select_active:
            self.update_undo_buffer(1)
            w = self.surface.get_width()
            h = self.surface.get_height()
            xp= [min(max(0,x),w) for x in self.select_xp]
            yp= [min(max(0,y),h) for y in self.select_yp]
            c_w= int(max(xp))-int(min(xp))
            c_h= int(max(yp))-int(min(yp))
            aux = cairo.ImageSurface(cairo.FORMAT_ARGB32, w,h)
            context = cairo.Context(aux)
            context.set_source_surface(self.surface,0,0)
            context.paint()
            context = cairo.Context(self.surface)
            context.set_source_surface(aux,-int(min(xp)),-int(min(yp)))
            context.paint()
            self.set_size(c_w,c_h)
            self.clear_overlay()
            self.print_tool()

    def is_modified(self):
        return self.modified

class FancyCanvas(Canvas):
    MARGIN = 0
    RSS = 0

    def __init__(self):
        # Initializing Canvas superclass
        super(FancyCanvas, self).__init__()

        # Resize Square Size
        self.RSS = 5
        # Margin (to draw shadows and resize squares)
        self.MARGIN = 20

        # Shadows to distribute around canvas (makes it more cute!)
        str = "GUI/bl-corner-shadow.png"
        self.BL_CORNER_SHADOW = cairo.ImageSurface.create_from_png(str)
        str = "GUI/tr-corner-shadow.png"
        self.TR_CORNER_SHADOW = cairo.ImageSurface.create_from_png(str)
        self.side_alpha_channels = [0.4, 0.39, 0.37, 0.32, 0.24, 0.16, 0.08, 0.04, 0.01]

        # Detecting decorations' color
        aux = gtk.Window()
        aux.realize()
        self.DECORATIONS_COLOR = aux.get_style().bg[gtk.STATE_SELECTED]

        # Basic Tools
        self.CANVAS_B_SCALER = tools.BothScalingTool(self)
        self.CANVAS_H_SCALER = tools.HorizontalScalingTool(self)
        self.CANVAS_V_SCALER = tools.VerticalScalingTool(self)

        # Useful constants
        self.RIGHT_SCALING_POINT = 0
        self.CORNER_SCALING_POINT = 1
        self.BOTTOM_SCALING_POINT = 2
        self.SCALING_SIDE_POINTS_MIN_SIZE = 20

        # Previous tool (to recover from a rescale)
        self.previous_tool = self.active_tool


    def set_size(self, width, height):
        self.width = max(width, 1)
        self.height = max(height, 1)
        self.set_size_request(self.width + self.MARGIN, self.height + self.MARGIN)


    def expose(self, widget, event):
        super(FancyCanvas, self).expose(widget, event)
        # Retrieving cairo context
        context = widget.window.cairo_create()
        # Modify clipping area to draw decorations outside the canvas
        # Draw decorations
        self.__draw_shadows(context)
        self.__draw_scaling_points(context)

    def button_pressed(self, widget, event):
        self.previous_tool = self.active_tool
        # When the click is outside the canvas, a scaling point might have been
        # clicked.
        if event.x >= self.width or event.y >= self.height:
            if self.width < self.SCALING_SIDE_POINTS_MIN_SIZE and self.height < self.SCALING_SIDE_POINTS_MIN_SIZE:
                if self.__over_scaling_point(self.CORNER_SCALING_POINT, event):
                    self.active_tool = self.CANVAS_B_SCALER
                else:
                    self.active_tool = self.DUMMY_TOOL
            elif self.width < self.SCALING_SIDE_POINTS_MIN_SIZE:
                if self.__over_scaling_point(self.RIGHT_SCALING_POINT, event):
                    self.active_tool = self.CANVAS_H_SCALER
                elif self.__over_scaling_point(self.CORNER_SCALING_POINT, event):
                    self.active_tool = self.CANVAS_B_SCALER
                else:
                    self.active_tool = self.DUMMY_TOOL
            elif self.height < self.SCALING_SIDE_POINTS_MIN_SIZE:
                if self.__over_scaling_point(self.BOTTOM_SCALING_POINT, event):
                    self.active_tool = self.CANVAS_V_SCALER
                elif self.__over_scaling_point(self.CORNER_SCALING_POINT, event):
                    self.active_tool = self.CANVAS_B_SCALER
                else:
                    self.active_tool = self.DUMMY_TOOL
            else:
                if self.__over_scaling_point(self.BOTTOM_SCALING_POINT, event):
                    self.active_tool = self.CANVAS_V_SCALER
                elif self.__over_scaling_point(self.RIGHT_SCALING_POINT, event):
                    self.active_tool = self.CANVAS_H_SCALER
                elif self.__over_scaling_point(self.CORNER_SCALING_POINT, event):
                    self.active_tool = self.CANVAS_B_SCALER
                else:
                    self.active_tool = self.DUMMY_TOOL
            if self.active_tool.name != 'NotSet':
                super(FancyCanvas, self).button_pressed(widget, event)

        else:
            super(FancyCanvas, self).button_pressed(widget, event)


    def __over_scaling_point(self, point, event):
        if point == self.CORNER_SCALING_POINT:
            if self.width < event.x < self.width + self.RSS + 2:
                if self.height-2 < event.y < self.height + self.RSS + 3:
                    return True

        if point == self.BOTTOM_SCALING_POINT:
            if self.width/2-2 < event.x < self.width/2 + self.RSS + 2:
                if self.height < event.y < self.height + self.RSS + 3:
                    return True

        if point == self.RIGHT_SCALING_POINT:
            if self.width < event.x < self.width + self.RSS + 2:
                if self.height/2 - 2 < event.y < self.height/2 + self.RSS + 3:
                    return True

        return False


    def button_released(self, widget, event):
        super(FancyCanvas, self).button_released(widget, event)
        self.active_tool = self.previous_tool


    def motion_event(self, widget, event):
        if self.__over_scaling_point(self.CORNER_SCALING_POINT, event):
            self.CANVAS_B_SCALER.select()
        elif self.__over_scaling_point(self.RIGHT_SCALING_POINT, event):
            self.CANVAS_H_SCALER.select()
        elif self.__over_scaling_point(self.BOTTOM_SCALING_POINT, event):
            self.CANVAS_V_SCALER.select()
        else:
            super(FancyCanvas, self).motion_event(widget, event)


    def __draw_shadows(self, context):
        # Shadow displacements
        disp = 2
        csw = self.BL_CORNER_SHADOW.get_width()

        if self.width > 10:
            # Bottom left corner
            context.set_source_surface(self.BL_CORNER_SHADOW, disp, self.height)
            context.paint()

            # Bottom shadow
            context.translate(0, self.height)
            for i in range(len(self.side_alpha_channels)):
                alpha = self.side_alpha_channels[i]
                context.rectangle(disp+csw, i, self.width-disp-csw, 1)
                context.set_source_rgba(0, 0, 0, alpha)
                context.fill()
            context.translate(0, -self.height)

        if self.height > 10:
            # Top right corner
            context.set_source_surface(self.TR_CORNER_SHADOW, self.width, disp)
            context.paint()

            # Side shadow
            context.translate(self.width, 0)
            for i in range(len(self.side_alpha_channels)):
                alpha = self.side_alpha_channels[i]
                context.rectangle(i, disp+csw, 1, self.height-disp-csw)
                context.set_source_rgba(0, 0, 0, alpha)
                context.fill()
            context.translate(-self.width, 0)


    def __draw_scaling_points(self, context):
        # Set the scaling points' color

        # Right scaling point
        if self.height > self.SCALING_SIDE_POINTS_MIN_SIZE:
            self.__draw_scaling_point(context, self.width,
               int(math.floor(self.height/2)))

        # Bottom scaling point
        if self.width > self.SCALING_SIDE_POINTS_MIN_SIZE:
            self.__draw_scaling_point(context, int(math.floor(self.width/2)),
               self.height)

        # Corner scaling point
        self.__draw_scaling_point(context, self.width, self.height)


    def __draw_scaling_point(self, context, x, y):
        # Base color
        context.set_source_color(self.DECORATIONS_COLOR)
        context.rectangle(x, y, self.RSS+2, self.RSS+2)
        context.fill()

        # Darker
        context.set_source_rgba(0, 0, 0, 0.4)
        context.rectangle(x, y, self.RSS+2, self.RSS+2)
        context.fill()

        # Base color
        context.set_source_color(self.DECORATIONS_COLOR)
        context.rectangle(x, y, self.RSS+1, self.RSS+1)
        context.fill()

        # Lighter
        context.set_source_rgba(1, 1, 1, 0.4)
        context.rectangle(x, y, self.RSS+1, self.RSS+1)
        context.fill()

        # The point itself
        context.set_source_color(self.DECORATIONS_COLOR)
        context.rectangle(x+1, y+1, self.RSS, self.RSS)
        context.fill()


gobject.signal_new("color_pick_event", Canvas, gobject.SIGNAL_RUN_FIRST, gobject.TYPE_NONE, (gobject.TYPE_PYOBJECT,))
# change whether GUI icons are enabled
gobject.signal_new("change_sensitivty", Canvas, gobject.SIGNAL_RUN_FIRST, gobject.TYPE_NONE, (gobject.TYPE_PYOBJECT,))