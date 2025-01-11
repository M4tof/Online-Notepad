import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog
import json
import asyncio

# File to store addresses
ADDRESSES_FILE = "addresses.json"

# Global variables
selected_ip = None
selected_port = None
current_file = None

# Variable to store previous cursor position and start position
prev_cursor_position = "1.0"  # Initializing at the start of the document
start_cursor_position = "1.0"  # Initialize the start position for changes

addresses = []
active_connection = None  # Stores the active TCP connection
file_sent_to_server = False  # Flag to ensure the file name is sent only once

# Async function to establish a TCP connection
async def establish_connection(ip, port):
    global active_connection, file_sent_to_server, current_file

    try:
        reader, writer = await asyncio.open_connection(ip, int(port))
        messagebox.showinfo("Connection", f"Successfully connected to {ip}:{port}")
        active_connection = writer

        # If a file is already open, send the file name
        if current_file and not file_sent_to_server:
            file_name = current_file.split("/")[-1]
            writer.write(file_name.encode() + b"\n")
            await writer.drain()
            file_sent_to_server = True
            print(f"File name '{file_name}' sent to server.")

    except Exception as e:
        messagebox.showerror("Connection Failed", f"Failed to connect to {ip}:{port}\nError: {e}")
        active_connection = None

async def send_to_server(data):
    global active_connection
    if active_connection:
        try:
            active_connection.write(data.encode() + b"\n")
            await active_connection.drain()  # Ensure data is sent
            print(f"Sent to server: {data}")
        except Exception as e:
            print(f"Error sending to server: {e}")
    else:
        print("No active connection to send data.")

# Wrapper for running the asyncio connection
def connect_to_address():
    global selected_ip, selected_port
    if not selected_ip or not selected_port:
        messagebox.showinfo("No Address Selected", "Please select an address to connect.")
        return

    # Run the asyncio connection in the event loop
    asyncio.run(establish_connection(selected_ip, selected_port))

def open_file():
    global current_file, active_connection, file_sent_to_server

    file_path = filedialog.askopenfilename(
        title="Open File",
        filetypes=[("Text Files", "*.txt"), ("All Files", "*.*")]
    )
    if file_path:
        try:
            with open(file_path, 'r') as file:
                content = file.read()
            text_widget.delete("1.0", tk.END)
            text_widget.insert(tk.END, content)
            root.title(f"Notepad - {file_path}")
            current_file = file_path

            # Enable "Connect to Address" menu option
            settings_menu.entryconfig("Connect to Address", state=tk.NORMAL)

        except Exception as e:
            messagebox.showerror("Error", f"Failed to open file: {e}")


def refresh_file():
    if current_file:
        try:
            with open(current_file, 'r') as file:
                content = file.read()
            text_widget.delete("1.0", tk.END)
            text_widget.insert(tk.END, content)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to refresh file: {e}")
    else:
        messagebox.showinfo("No File", "No file is currently open to refresh.")

def save_file_content(event=None):
    if current_file:
        try:
            content = text_widget.get("1.0", tk.END)
            with open(current_file, 'w') as file:
                file.write(content.rstrip())
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save file: {e}")

def print_cursor_position(event=None):
    global prev_cursor_position, start_cursor_position, active_connection

    current_cursor_position = text_widget.index(tk.INSERT)

    # If the cursor has moved from the start of the change, update the start position
    if event:
        start_cursor_position = prev_cursor_position

    if prev_cursor_position != current_cursor_position:
        # Capture the full range from start to current position
        left_position = start_cursor_position
        right_position = current_cursor_position

        if left_position > right_position:
            left_position, right_position = right_position, left_position

        start_line, start_col = map(int, left_position.split('.'))
        end_line, end_col = map(int, right_position.split('.'))

        # Initialize text_range to capture all changes
        text_range = ""

        if start_line == end_line:
            # If it's on the same line
            text_range = text_widget.get(left_position, right_position)
        else:
            # 1. Capture text from start cursor position to the end of the start line
            text_range = text_widget.get(left_position, f"{start_line + 1}.0")
            
            # 2. Loop through the lines in between and capture their entire text
            for line in range(start_line + 1, end_line):
                text_range += text_widget.get(f"{line}.0", f"{line + 1}.0")
            
            # 3. Capture text from the start of the end line to the current cursor position
            text_range += text_widget.get(f"{end_line}.0", right_position)

        # Prepare the string to be sent in the format: X1.Y1.X2.Y2.xxxxxxyyyyyzzzzz
        formatted_string = f"{start_line}.{start_col}.{end_line}.{end_col}.{text_range}"

        # Send to server asynchronously if connected
        if active_connection:
            asyncio.run(send_to_server(formatted_string))

        # Log the change locally
        print(f"Text change from {left_position} to {right_position}:")
        print(text_range)

    # Update the previous cursor position
    prev_cursor_position = current_cursor_position



def load_addresses():
    try:
        with open(ADDRESSES_FILE, 'r') as file:
            return json.load(file)
    except (FileNotFoundError, json.JSONDecodeError):
        return []

def save_addresses(addresses):
    try:
        with open(ADDRESSES_FILE, 'w') as file:
            json.dump(addresses, file, indent=4)
    except Exception as e:
        messagebox.showerror("Error", f"Failed to save addresses: {e}")

def open_settings():
    settings_window = tk.Toplevel(root)
    settings_window.title("Manage Addresses")

    address_listbox = tk.Listbox(settings_window, height=10, width=50)
    address_listbox.pack(pady=10)

    def refresh_address_list():
        address_listbox.delete(0, tk.END)
        for addr in addresses:
            address_listbox.insert(tk.END, f"{addr['name']} - {addr['ip']}:{addr['port']}")

    def add_address():
        name = simpledialog.askstring("Add Address", "Enter name:")
        ip = simpledialog.askstring("Add Address", "Enter IP address:")
        port = simpledialog.askstring("Add Address", "Enter port:")

        if name and ip and port:
            addresses.append({"name": name, "ip": ip, "port": port})
            save_addresses(addresses)
            refresh_address_list()
        else:
            messagebox.showinfo("Incomplete", "All fields are required.")

    def delete_address():
        selected = address_listbox.curselection()
        if selected:
            index = selected[0]
            del addresses[index]
            save_addresses(addresses)
            refresh_address_list()
        else:
            messagebox.showinfo("No Selection", "Select an address to delete.")
    
    def on_address_click(event):
        selected = address_listbox.curselection()
        if selected:
            index = selected[0]
            selected_address = addresses[index]
            global selected_ip, selected_port
            selected_ip = selected_address['ip']
            selected_port = selected_address['port']
            print(f"Selected IP: {selected_ip}, Port: {selected_port}")

    address_listbox.bind("<ButtonRelease-1>", on_address_click)
    tk.Button(settings_window, text="Add Address", command=add_address).pack(pady=5)
    tk.Button(settings_window, text="Delete Address", command=delete_address).pack(pady=5)

    refresh_address_list()

# Initialize the main window
root = tk.Tk()
root.title("Notepad")

# Create the text widget
text_widget = tk.Text(root, wrap=tk.WORD, undo=True)
text_widget.pack(fill=tk.BOTH, expand=True)

# Scrollbar for the text widget
scrollbar = tk.Scrollbar(root, command=text_widget.yview)
scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
text_widget.config(yscrollcommand=scrollbar.set)

# Set up the menu
menu_bar = tk.Menu(root)

# File menu
file_menu = tk.Menu(menu_bar, tearoff=0)
file_menu.add_command(label="Open", command=open_file)
file_menu.add_command(label="Refresh", command=refresh_file)
menu_bar.add_cascade(label="File", menu=file_menu)

# Settings menu
settings_menu = tk.Menu(menu_bar, tearoff=0)
settings_menu.add_command(label="Manage Addresses", command=open_settings)
settings_menu.add_command(label="Connect to Address", command=connect_to_address, state=tk.DISABLED)  # Initially disabled
menu_bar.add_cascade(label="Settings", menu=settings_menu)

root.config(menu=menu_bar)

# Track changes and save automatically
text_widget.bind("<KeyRelease>", lambda e: (save_file_content(), print_cursor_position(e)))
text_widget.bind("<ButtonRelease>", print_cursor_position)

# Load saved addresses
addresses = load_addresses()

# Start the application
root.mainloop()