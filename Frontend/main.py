import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog
import json
import asyncio

# File to store options
ADDRESSES_FILE = "settings.json"

# Global variables
SELECTED_IP = None
SELECTED_PORT = None
CURRENT_FILE = None
USERNAME = "Guest"

# Variable to store previous cursor position and start position
PREV_CURSOR_POSITION = "1.0"  # Initializing at the start of the document
START_CURSOR_POSITION = "1.0"  # Initialize the start position for changes

ADDRESSES = []
active_connection = None  # Stores the active TCP connection
file_sent_to_server = False  # Flag to ensure the file name is sent only once

async def manage_connection():
    global active_connection, file_sent_to_server, CURRENT_FILE, SELECTED_IP, SELECTED_PORT,USERNAME

    if active_connection:
        messagebox.showinfo("Connection", "A connection is already active.")
        return

    # Validation checks
    if not SELECTED_IP or not SELECTED_PORT:
        messagebox.showerror("Error", "Server address not selected.")
        return
    if not CURRENT_FILE:
        messagebox.showerror("Error", "No file is open.")
        return
    if not USERNAME:
        messagebox.showerror("Error", "Username is not set.")
        return

    try:
        # Establish connection
        reader, writer = await asyncio.open_connection(SELECTED_IP, int(SELECTED_PORT))
        messagebox.showinfo("Connection", f"Successfully connected to {SELECTED_IP}:{SELECTED_PORT}")
        active_connection = writer

        # Send initial message: username|filename.extension
        file_name = CURRENT_FILE.split("/")[-1]
        initial_message = f"{file_name}|{USERNAME}"
        writer.write(initial_message.encode() + b"\n")
        await writer.drain()
        print(f"Sent to server: {initial_message}")

        # Wait for a response (number of lines to replace)
        response = await reader.readline()
        num_lines = int(response.decode().strip())
        print(f"Received number of lines to replace: {num_lines}")

        new_lines = []
        for _ in range(num_lines):
            line = await reader.readline()
            new_lines.append(line.decode().rstrip())

        if CURRENT_FILE:
            with open(CURRENT_FILE, 'r') as file:
                current_lines = file.readlines()

            # Replace existing lines and add new ones if needed
            for i in range(len(new_lines)):
                if i < len(current_lines):
                    current_lines[i] = new_lines[i] + "\n"  # Overwrite line
                else:
                    current_lines.append(new_lines[i] + "\n")  # Append new line

            # Remove extra lines if server data has fewer lines
            current_lines = current_lines[:len(new_lines)]

            # Save updated content to the file
            with open(CURRENT_FILE, 'w') as file:
                file.writelines(current_lines)

            # Update the text widget
            text_widget.delete("1.0", tk.END)
            text_widget.insert(tk.END, "".join(current_lines))

            print("File updated with new lines from the server.")

    except Exception as e:
        messagebox.showerror("Connection Failed", f"Failed to communicate with the server.\nError: {e}")
        active_connection = None
    finally:
        if active_connection:
            active_connection.close()
            active_connection = None

def connect_to_address():
    # Run the asyncio connection in the event loop
    asyncio.run(manage_connection())

def open_file():
    global CURRENT_FILE, active_connection, file_sent_to_server

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
            CURRENT_FILE = file_path

            # Enable "Connect to Address" menu option
            settings_menu.entryconfig("Connect to Address", state=tk.NORMAL)

        except Exception as e:
            messagebox.showerror("Error", f"Failed to open file: {e}")

def refresh_file():
    if CURRENT_FILE:
        try:
            with open(CURRENT_FILE, 'r') as file:
                content = file.read()
            text_widget.delete("1.0", tk.END)
            text_widget.insert(tk.END, content)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to refresh file: {e}")
    else:
        messagebox.showinfo("No File", "No file is currently open to refresh.")

def save_file_content(event=None):
    if CURRENT_FILE:
        try:
            content = text_widget.get("1.0", tk.END)
            with open(CURRENT_FILE, 'w') as file:
                file.write(content.rstrip())
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save file: {e}")

def print_change(event=None):
    global PREV_CURSOR_POSITION, START_CURSOR_POSITION, active_connection

    current_cursor_position = text_widget.index(tk.INSERT)

    # If the cursor has moved from the start of the change, update the start position
    if event:
        START_CURSOR_POSITION = PREV_CURSOR_POSITION

    if PREV_CURSOR_POSITION != current_cursor_position:
        # Capture the full range from start to current position
        left_position = START_CURSOR_POSITION
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
        formatted_string = f"1.{start_line}.{start_col}.{end_line}.{end_col}.{text_range}"

        # Send to server asynchronously if connected
        if active_connection:
            asyncio.run(send_to_server(formatted_string))

        # Log the change locally
        print(f"Text change from {left_position} to {right_position}:")
        print(text_range)

    # Update the previous cursor position
    PREV_CURSOR_POSITION = current_cursor_position

def load_addresses():
    try:
        with open(ADDRESSES_FILE, 'r') as file:
            data = json.load(file)
            global SELECTED_IP, SELECTED_PORT, USERNAME
            if "last_selected" in data:
                SELECTED_IP = data["last_selected"].get("ip")
                SELECTED_PORT = data["last_selected"].get("port")
                USERNAME = data["last_selected"].get("username", "Guest")
                print(f"Loaded last selected IP: {SELECTED_IP}, Port: {SELECTED_PORT}, Username: {USERNAME}")
            return data.get("addresses", [])
    except (FileNotFoundError, json.JSONDecodeError):
        return []

def save_addresses(addresses):
    try:
        data = {"addresses": addresses}
        if SELECTED_IP and SELECTED_PORT:
            data["last_selected"] = {
                "ip": SELECTED_IP,
                "port": SELECTED_PORT,
                "username": USERNAME,  # Save the updated username
            }
        with open(ADDRESSES_FILE, 'w') as file:
            json.dump(data, file, indent=4)
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
            global SELECTED_IP, SELECTED_PORT
            SELECTED_IP = selected_address['ip']
            SELECTED_PORT = selected_address['port']
            print(f"Selected IP: {SELECTED_IP}, Port: {SELECTED_PORT}")
            save_addresses(addresses)  # Save the last selected address

    address_listbox.bind("<ButtonRelease-1>", on_address_click)

    tk.Button(settings_window, text="Add Address", command=add_address).pack(pady=5)
    tk.Button(settings_window, text="Delete Address", command=delete_address).pack(pady=5)

    refresh_address_list()

def change_username():
    global USERNAME
    new_username = simpledialog.askstring("Change Username", "Enter your username:", initialvalue=USERNAME)
    if new_username:
        USERNAME = new_username
        save_addresses(addresses)  # Save updated username to JSON
        print(f"Username updated to: {USERNAME}")
    else:
        messagebox.showinfo("Invalid Input", "Username cannot be empty.")

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
settings_menu.add_command(label="Change Username", command=change_username)
settings_menu.add_command(label="Connect to Address", command=connect_to_address, state=tk.DISABLED)  # Initially disabled until file is opened
menu_bar.add_cascade(label="Settings", menu=settings_menu)

root.config(menu=menu_bar)

# Track changes and save automatically
text_widget.bind("<KeyRelease>", lambda e: (save_file_content(), print_change(e)))
text_widget.bind("<ButtonRelease>", print_change)

# Load saved addresses
addresses = load_addresses()

# Start the application
root.mainloop()