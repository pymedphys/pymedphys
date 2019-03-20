import tkinter as tk
from tkinter.filedialog import askopenfilename
from matplotlib.backends.backend_tkagg import (
    FigureCanvasTkAgg, NavigationToolbar2Tk)
from matplotlib.backend_bases import key_press_handler
from matplotlib.figure import Figure
from pymedphys._labs.paulking.profile import Profile

""" Graphical User Interface for Profile Class """


class Application(tk.Frame):
    def __init__(self, parent, *args, **kwargs):
        tk.Frame.__init__(self, parent, *args, **kwargs)
        self.parent = parent
        root.wm_title("Profile Tool")

        fig = Figure(figsize=(5, 4), dpi=100)
        self.subplot = fig.add_subplot(111)

        self.canvas = FigureCanvasTkAgg(fig, master=root)
        self.canvas.draw()
        self.canvas.get_tk_widget().pack(side=tk.TOP, fill=tk.BOTH, expand=1)

        self.toolbar = NavigationToolbar2Tk(self.canvas, root)
        self.toolbar.update()
        self.canvas.get_tk_widget().pack(side=tk.TOP, fill=tk.BOTH, expand=1)
        self.canvas.mpl_connect("key_press_event", self.on_key_press)

        self.buttons = []
        self.button_bar = tk.Frame(self)
        self.button_bar.pack(side=tk.BOTTOM, fill="both", expand=True)
        self.button = None

        self.status = tk.Label(self, bd=1, relief=tk.SUNKEN, anchor=tk.W)
        self.status.pack(fill=tk.X)
        self.status_set('Ready.')

        self.from_palette = (
            c for c in ['red', 'green', 'orange', 'blue', 'yellow', 'purple1',
                        'red', 'green', 'orange', 'blue', 'yellow', 'purple1'])
        self.next_color = None

    # BUTTON CALLBACK TO SELECT A CURRENT CURVE FOR EDITING

        menu = tk.Menu(root)
        root.config(menu=menu)
        menu = self.populate(menu)

    def add_buttom(self):
        self.button = tk.Button(master=self.button_bar,
                                bg=self.next_color,
                                text="  ",
                                command=self._quit)
        self.button.pack(side=tk.LEFT, fill='both')

    def status_set(self, msg, *args):
        self.status.config(text=msg % args)
        self.status.update_idletasks()

    def status_clear(self):
        self.status.config(text="")
        self.status.update_idletasks()

    def populate(self, menu):
        """ """

        filemenu = tk.Menu(menu)
        menu.add_cascade(label="File", menu=filemenu)
        filemenu.add_command(label="Open PRS",
                             command=self.profiler_file)
        filemenu.add_command(label="Open PNG",
                             command=self.film_file)
        filemenu.add_command(label="Make Pulse",
                             command=self.create_pulse)
        filemenu.add_separator()
        filemenu.add_command(label="Exit", command=root.quit)

        editmenu = tk.Menu(menu)
        menu.add_cascade(label="Edit", menu=editmenu)
        editmenu.add_command(label="Norm Dose", command=self.profiler_file)
        editmenu.add_command(label="Norm X", command=self.film_file)
        editmenu.add_command(label="Resample", command=self.stub)
        editmenu.add_command(label="Resample Y", command=self.stub)
        editmenu.add_command(label="Flip", command=self.stub)
        editmenu.add_command(label="Normalise", command=self.stub)
        editmenu.add_command(label="2X/W", command=self.stub)
        editmenu.add_command(label="Symmetrise", command=self.stub)

        getmenu = tk.Menu(menu)
        menu.add_cascade(label="Get", menu=getmenu)
        getmenu.add_command(label="Edges", command=self.stub)
        getmenu.add_command(label="Flatness", command=self.stub)
        getmenu.add_command(label="Symmetry", command=self.stub)
        getmenu.add_command(label="X", command=self.stub)
        getmenu.add_command(label="Y", command=self.stub)
        getmenu.add_command(label="Segment", command=self.stub)
        getmenu.add_command(label="Shoulders", command=self.stub)
        getmenu.add_command(label="Tails", command=self.stub)
        getmenu.add_command(label="Umbra", command=self.stub)

        helpmenu = tk.Menu(menu)
        menu.add_cascade(label="Help", menu=helpmenu)
        helpmenu.add_command(label="About...", command=self.about)
        return menu

    def on_key_press(self, event):
        print("you pressed {}".format(event.key))
        key_press_handler(event, self.canvas, self.toolbar)

    def _quit(self):
        root.quit()
        root.destroy()

    def stub(self):
        pass

    def profiler_file(self):
        filename = askopenfilename(
            initialdir="/", title="SNC Profiler",
            filetypes=(("Profiler Files", "*.prs"), ("all files", "*.*")))

        profiler = Profile().from_snc_profiler(filename, 'rad')
        self.subplot.plot(profiler.x, profiler.y)
        self.canvas.draw()
        self.next_color = next(self.from_palette)
        self.add_buttom()

        profiler = Profile().from_snc_profiler(filename, 'tvs')
        self.subplot.plot(profiler.x, profiler.y, color=self.next_color)
        self.canvas.draw()
        self.next_color = next(self.from_palette)
        self.add_buttom()

        self.canvas.draw()

    def film_file(self):
        filename = askopenfilename(
            initialdir="/", title="Film File",
            filetypes=(("Film Files", "*.png"), ("all files", "*.*")))
        profiler = Profile().from_narrow_png(filename)
        self.subplot.plot(profiler.x, profiler.y)
        self.canvas.draw()

    def create_pulse(self):

        pulse_window = tk.Tk()
        pulse_window.title("Parameters")
        pulse_window.grid()
        heading = tk.Label(pulse_window, text='Pulse Parameters')
        heading.grid(row=0, column=0, columnspan=2)
        # centre
        label = tk.Label(pulse_window, text="   Centre:", anchor=tk.E)
        label.grid(column=0, row=1)
        centre = tk.DoubleVar(pulse_window, value=0.0)
        centre_entry = tk.Entry(pulse_window, width=10, textvariable=centre)
        centre_entry.grid(column=1, row=1)
        # width
        label = tk.Label(pulse_window, text="    Width:")
        label.grid(column=0, row=2)
        width = tk.DoubleVar(pulse_window, value=10.0)
        width_entry = tk.Entry(pulse_window, width=10, textvariable=width)
        width_entry.grid(column=1, row=2)
        # domain, start
        label = tk.Label(pulse_window, text="    Start:")
        label.grid(column=0, row=3)
        start = tk.DoubleVar(pulse_window, value=-10.0)
        start_entry = tk.Entry(pulse_window, width=10, textvariable=start)
        start_entry.grid(column=1, row=3)
        # domain, end
        label = tk.Label(pulse_window, text="      End:")
        label.grid(column=0, row=4)
        end = tk.DoubleVar(pulse_window, value=10.0)
        end_entry = tk.Entry(pulse_window, width=10, textvariable=end)
        end_entry.grid(column=1, row=4)
        # increment
        label = tk.Label(pulse_window, text="Increment:")
        label.grid(column=0, row=5)
        increment = tk.DoubleVar(pulse_window, value=0.1)
        increment_entry = tk.Entry(
            pulse_window, width=10, textvariable=increment)
        increment_entry.grid(column=1, row=5)
        # OK Button

        def OK():
            # pulse_window.quit()
            profile = Profile().from_pulse(centre.get(), width.get(),
                                           (start.get(), end.get()), increment.get())
            self.subplot.plot(profile.x, profile.y)
            self.canvas.draw()
            pulse_window.destroy()
        ok_button = tk.Button(pulse_window, text="OK", command=OK)
        ok_button.grid(column=0, row=6, columnspan=2)

        pulse_window.mainloop()

    def about(self):
        tk.messagebox.showinfo(
            "About", "Profile Tool \n king.r.paul@gmail.com")


if __name__ == "__main__":
    root = tk.Tk()
    Application(root).pack(side="top", fill="both", expand=True)
    root.mainloop()
