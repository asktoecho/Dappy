import cairo
import gtk
import gobject


from lib.tools.generic import *
from rgbacolor import RGBAColor

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
        
class senstivity_data:
    
    def __init__(self,action,sensitive):
        self.action = action
        self.sensitive = sensitive

class Canvas(gtk.DrawingArea):
    TRANSPARENT_IMAGE = 0
    OPAQUE_IMAGE = 1

    DEFAULT_CURSOR = gtk.gdk.Cursor(gtk.gdk.ARROW)
    active_tool = None
    printing_tool = False
    image_type = 0
    picker_col = None
    
    UNDO_BUFFER = undoBuffer()
    


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
        self.ALPHA_PATTERN = cairo.SurfacePattern(cairo.ImageSurface.create_from_png("pixmaps/alpha-pattern.png"))
        self.ALPHA_PATTERN.set_extend(cairo.EXTEND_REPEAT)

        # Basic tools
        self.DUMMY_TOOL = Tool(self)
        self.active_tool = self.DUMMY_TOOL

        # Surface is the space in the canvas
        self.surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, self.width, self.height)
        

    def reset(self, context):
        # Clipping to draw area
        context.rectangle(0, 0, self.width, self.height)
        context.clip()


    def set_size(self, width, height):
        self.width = max(width, 1)
        self.height = max(height, 1)
        self.set_size_request(self.width, self.height)


    def get_width(self):
        return self.width


    def get_height(self):
        return self.height


    def set_active_tool(self, tool):
        self.active_tool = tool


    def expose(self, widget, event):
        context = widget.window.cairo_create()

        self.draw(context)


    def button_pressed(self, widget, event):
        if event.type == gtk.gdk.BUTTON_PRESS:
            self.active_tool.begin(event.x, event.y,event.button)
            


    def button_released(self, widget, event):
        self.active_tool.end(event.x, event.y)
        self.swap_buffers()
        self.active_tool.commit()
        if self.active_tool.name == "ColorPicker":
            col = self.active_tool.col
            self.picker_col =  RGBAColor(col[2], col[1], col[0], col[3])
            self.emit("color_pick_event", event)
        

    def move_event(self, widget, event):
        #context = widget.window.cairo_create()
        self.active_tool.move(event.x, event.y)
        if self.active_tool.name == "ColorPicker" and  self.active_tool.mode == self.active_tool.DRAWING:
            col = self.active_tool.col
            self.picker_col =  RGBAColor(col[2], col[1], col[0], col[3])
            self.emit("color_pick_event", event)
        else:
            self.swap_buffers()
        


    def motion_event(self, widget, event):
        self.active_tool.select()
        if event.x > self.width or event.y > self.height:
            self.window.set_cursor(self.DEFAULT_CURSOR)


    def print_tool(self):
        aux = cairo.ImageSurface(cairo.FORMAT_ARGB32, self.width, self.height)
        context = cairo.Context(aux)
        self.printing_tool = True
        self.draw(context)
        self.surface = aux
        self.printing_tool = False
        


    def draw(self, context):
        # Clipping area
        self.reset(context)

        # Drawing the background
        if not self.printing_tool:
            self.__draw_background(context)

        if self.image_type == self.OPAQUE_IMAGE and self.printing_tool:
            self.__draw_background(context)

        # Draw the result
        self.reset(context)

        source = context.get_source()
        context.set_source_surface(self.surface)
        context.paint()
        context.set_source(source)

        self.active_tool.draw(context)


    def __draw_background(self, context):
        context.rectangle(0, 0, self.width, self.height)
        if self.image_type == self.TRANSPARENT_IMAGE:
            context.set_source(self.ALPHA_PATTERN)
            context.paint()
        else:
            context.set_source_rgb(1, 1, 1)
            context.fill()


    def swap_buffers(self):
        rect = gtk.gdk.Rectangle(0, 0, self.width, self.height)
        self.window.invalidate_rect(rect, True)
        


    def get_image(self):
        return self.surface


    def set_image(self, surface):
        self.surface = surface
        self.set_size(surface.get_width(), surface.get_height())


    def set_image_type(self, image_type):
        self.image_type = image_type
        
    def get_color(self):
        return self.picker_col
        
    def undo(self):
    
        if self.UNDO_BUFFER.n_buf_full>0:
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
        
#    def paste(self):
        

gobject.signal_new("color_pick_event", Canvas, gobject.SIGNAL_RUN_FIRST, gobject.TYPE_NONE, (gobject.TYPE_PYOBJECT,))
gobject.signal_new("change_sensitivty", Canvas, gobject.SIGNAL_RUN_FIRST, gobject.TYPE_NONE, (gobject.TYPE_PYOBJECT,))