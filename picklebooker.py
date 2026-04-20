import threading
from datetime import datetime
from tkinter import *
from tkinter import messagebox, ttk

from autobook import autobook, booking_window_date, is_too_early


def run_autobook(*args):
    if not validate_inputs():
        return

    d = date.get()

    # Handle "too early" case with a dialog instead of CLI input()
    if is_too_early(d):
        run_date = booking_window_date(d)
        proceed = messagebox.askyesno(
            "Too Early",
            f"Booking window for {d} doesn't open until {run_date}.\nProceed anyway?",
        )
        if not proceed:
            return

    # Disable the button so it can't be clicked again
    book_button.config(state=DISABLED)
    status_var.set("Starting...")

    def on_status(msg):
        # Schedule the label update on the main thread
        root.after(0, lambda: status_var.set(msg))

    def target():
        try:
            autobook(
                d,
                time.get(),
                int(court.get()),
                int(duration.get()),
                on_status=on_status,
            )
            root.after(0, on_success)
        except SystemExit:
            root.after(
                0, lambda: on_error("Booking failed. Check the terminal for details.")
            )
        except Exception as e:
            root.after(0, lambda: on_error(str(e)))

    thread = threading.Thread(target=target, daemon=True)
    thread.start()


def on_success():
    messagebox.showinfo(title="Success", message="Booking complete!")
    root.destroy()


def on_error(msg):
    status_var.set("Failed")
    book_button.config(state=NORMAL)
    messagebox.showerror("Error", msg)


def validate_inputs():
    try:
        datetime.strptime(date.get(), "%Y-%m-%d")
    except ValueError:
        messagebox.showerror("Invalid Input", "Date must be in YYYY-MM-DD format.")
        return False

    try:
        datetime.strptime(time.get(), "%H:%M")
    except ValueError:
        messagebox.showerror("Invalid Input", "Time must be in HH:MM (24-hour) format.")
        return False

    if court.get() not in ("1", "2", "3"):
        messagebox.showerror("Invalid Input", "Court must be 1, 2, or 3.")
        return False

    if duration.get() not in ("30", "60", "90"):
        messagebox.showerror("Invalid Input", "Duration must be 30, 60, or 90 minutes.")
        return False

    return True


root = Tk()
root.title("Picklebooker")

mainframe = ttk.Frame(root, padding="3 3 12 12")
mainframe.grid(column=0, row=0, sticky=(N, W, E, S))
root.columnconfigure(0, weight=1)
root.rowconfigure(0, weight=1)

date = StringVar(value=datetime.now().strftime("%Y-%m-%d"))
date_entry = ttk.Entry(mainframe, width=12, textvariable=date)
date_entry.grid(column=1, row=1, sticky=(W, E))
ttk.Label(mainframe, text="Date").grid(column=2, row=1, sticky=(W, E))

time = StringVar()
time_entry = ttk.Entry(mainframe, width=12, textvariable=time)
time_entry.grid(column=1, row=2, sticky=(W, E))
ttk.Label(mainframe, text="Time").grid(column=2, row=2, sticky=(W, E))

court = StringVar(value="3")
court_entry = ttk.Combobox(
    mainframe, width=12, textvariable=court, values=["1", "2", "3"]
)
court_entry.grid(column=1, row=3, sticky=(W, E))
ttk.Label(mainframe, text="Court").grid(column=2, row=3, sticky=(W, E))

duration = StringVar(value="90")
duration_entry = ttk.Combobox(
    mainframe, width=12, textvariable=duration, values=["30", "60", "90"]
)
duration_entry.grid(column=1, row=4, sticky=(W, E))
ttk.Label(mainframe, text="Duration").grid(column=2, row=4, sticky=(W, E))

book_button = ttk.Button(mainframe, text="Book", command=run_autobook)
book_button.grid(column=1, row=5, sticky=W)

status_var = StringVar()
status_label = ttk.Label(mainframe, textvariable=status_var, foreground="gray")
status_label.grid(column=2, row=5, sticky=W)

for child in mainframe.winfo_children():
    child.grid_configure(padx=5, pady=5)

date_entry.focus()

root.bind("<Return>", run_autobook)

root.mainloop()
