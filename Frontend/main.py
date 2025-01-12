import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog
import json
import threading
import queue
import socket

# Global variables
ADDRESSES_FILE = "settings.json"
BUFFER_SIZE = 5120
SELECTED_IP = None
SELECTED_PORT = None
CURRENT_FILE = None
USERNAME = "Guest"
USERS_LIST = []

# Variable to store previous cursor position and start position
PREV_CURSOR_POSITION = "1.0"
START_CURSOR_POSITION = "1.0"

# Communication queues
to_server_queue = queue.Queue()
from_server_queue = queue.Queue()  

# TCP connection thread
tcp_thread = None
tcp_running = threading.Event()

# TCP thread function
def tcp_connection(ip, port):
    global tcp_running
    try:
        # Connect to the server
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.connect((ip, int(port)))
            messagebox.showinfo("Connection", f"Connected to {ip}:{port}")
            
            # Initial setup
            file_name = CURRENT_FILE.split("/")[-1]
            initial_message = f"{file_name}|{USERNAME}"
            sock.sendall(initial_message.encode())

            # Synchronisation with master copy of the file
            line_count_data = sock.recv(BUFFER_SIZE).decode()
            line_count = int(line_count_data.strip())
            print(f"Server's master copy has {line_count} lines.")

            # Clear and replace the content of the text_widget
            content = ""
            for _ in range(line_count):
                line = sock.recv(BUFFER_SIZE).decode()
                content += line

            # Update text_widget and therfore the local copy safely 
            text_widget.replace("1.0", tk.END, content)

            print("Synchronized local copy with server's master copy.")
            
            # Start receiving and sending data
            while tcp_running.is_set():
                # Receive data from the server
                try:
                    sock.settimeout(0.1)  # Non-blocking receive
                    data = sock.recv(BUFFER_SIZE)
                    if data:
                        from_server_queue.put(data.decode())
                except socket.timeout:
                    pass  # No data received; continue

                # Send changes to the server
                while not to_server_queue.empty():
                    change = to_server_queue.get()
                    sock.sendall(change.encode())

    except Exception as e:
        messagebox.showerror("Error", f"TCP Connection error: {e}")
        tcp_running.clear()

# setup the tcp conection thread
def start_tcp_connection():
    global tcp_thread, tcp_running
    if SELECTED_IP and SELECTED_PORT:
        if not CURRENT_FILE:
            messagebox.showerror("Error", "No file is open.")
            return

        if not tcp_running.is_set():
            tcp_running.set()
            tcp_thread = threading.Thread(target=tcp_connection, args=(SELECTED_IP, SELECTED_PORT))
            tcp_thread.daemon = True  # Ensures the thread exits with the program
            tcp_thread.start()
            print("TCP thread started")
    else:
        messagebox.showerror("Error", "Server address not selected.")

def stop_tcp_connection():
    global tcp_running, USERNAME
    if tcp_running.is_set():

        # Send the disconnect message to the server
        disconnect_message = f"3.{USERNAME}"
        enqueue_change(disconnect_message)  # Enqueue the message to be sent

        #Wait for the children to end
        tcp_running.clear()
        if tcp_thread and tcp_thread.is_alive():
            tcp_thread.join()
        
        print("TCP thread stopped")

def enqueue_change(change):
    to_server_queue.put(change)

def process_server_messages():
    # Process messages from the server and update the GUI
    while not from_server_queue.empty():
        message = from_server_queue.get()

        #Raw form of recieved data
        print(f"From server: {message}")
        
        #Split the message by the standart . used, in case of 1 later parts might be concatenated
        message_parts = message.split(".")
        
        if not message_parts:
            continue

        # Extract the number (1, 2) to determine the action type
        try:
            message_type = int(message_parts[0])  # This will be 1 or 2
        except ValueError:
            continue  # If it cannot be parsed, skip it

        # Switch case behavior based on the first part (the message type)
        if message_type == 1:
            # Message type 1: Handle updates to the text file
            print("Handling message type 1: Text update")
            handle_text_update(message_parts[1:])

        elif message_type == 2:
            # Message type 2: Handle new user or first user list synch
            print("Handling message type 2: New user")
            users_handler(message_parts[1])
        
        else:
            print(f"Unknown message type: {message_type}")

    # Schedule the function to run again
    root.after(100, process_server_messages)

def handle_text_update(parts):
    print(f"Updating text with message parts: {parts}")
    
    if len(parts) >= 4:
        # Extract X1, Y1, X2, Y2 as integers from parts
        X1 = int(parts[0])
        Y1 = int(parts[1])
        X2 = int(parts[2])
        Y2 = int(parts[3])
        
        # Join the rest of the parts to reconstruct the text in case the text contained . or |
        text = ".".join(parts[4:])

        # Define the start and end positions in tkinter text format
        start_position = f"{X1}.{Y1}"
        end_position = f"{X2}.{Y2}"
        
        # Update the text_widget content within the specified range
        text_widget.delete(start_position, end_position)
        text_widget.insert(start_position, text)

        print(f"Updated local text from {start_position} to {end_position} with: '{text}'")
        
    else:
        print("Error: Insufficient parts in message to handle text update.")

def users_handler(parts):
    global USERS_LIST
    
    USERS_LIST = parts
    users = USERS_LIST.split('|')
    
    # Clear the existing items in the Listbox
    users_listbox.delete(0, tk.END)
    
    for user in users:
        users_listbox.insert(tk.END, user)
        
    print(f"Updated users list: {USERS_LIST}")

def open_file():
    global CURRENT_FILE

    #Default file type is .txt but other can be chosen
    file_path = filedialog.askopenfilename(
        title="Open File",
        filetypes=[("Text Files", "*.txt"), ("All Files", "*.*")]
    )

    if file_path:
        try:
            #Open the file and add it to the text_widget
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
    #Refresh the local copy of the file in case it was modified outside the client-server comunication
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
    # Save changes from client to the local file
    if CURRENT_FILE:
        try:
            content = text_widget.get("1.0", tk.END)
            with open(CURRENT_FILE, 'w') as file:
                file.write(content.rstrip())
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save file: {e}")

def print_change(event=None):
    global PREV_CURSOR_POSITION, START_CURSOR_POSITION

    current_cursor_position = text_widget.index(tk.INSERT)

    # If the cursor has moved from the start of the change, update the start position
    if event:
        START_CURSOR_POSITION = PREV_CURSOR_POSITION

    if PREV_CURSOR_POSITION != current_cursor_position:
        # Capture the full range from start to current position
        left_position = START_CURSOR_POSITION
        right_position = current_cursor_position

        #ensure the left position is infact the earlier one
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

        # Prepare the string to be sent in the format: 1.X1.Y1.X2.Y2.text
        formatted_string = f"1.{start_line}.{start_col}.{end_line}.{end_col}.{text_range}"

        # Log the change locally
        print(f"Text change {formatted_string}")

        # add the change to queue to be send further to the server
        enqueue_change(formatted_string)

    # Update the previous cursor position
    PREV_CURSOR_POSITION = current_cursor_position

def load_save_data():
    #Load data from settings.json
    try:
        with open(ADDRESSES_FILE, 'r') as file:
            data = json.load(file)
            global SELECTED_IP, SELECTED_PORT, USERNAME
            #copy the settings from the previous session
            if "last_selected" in data:
                SELECTED_IP = data["last_selected"].get("ip")
                SELECTED_PORT = data["last_selected"].get("port")
                USERNAME = data["last_selected"].get("username", "Guest")
                print(f"Loaded last selected IP: {SELECTED_IP}, Port: {SELECTED_PORT}, Username: {USERNAME}")
            return data.get("addresses", [])
    except (FileNotFoundError, json.JSONDecodeError):
        return []

def save_data(addresses):
    #save current session data to the settings file
    try:
        data = {"addresses": addresses}
        if SELECTED_IP and SELECTED_PORT:
            data["last_selected"] = {
                "ip": SELECTED_IP,
                "port": SELECTED_PORT,
                "username": USERNAME, 
            }
        with open(ADDRESSES_FILE, 'w') as file:
            json.dump(data, file, indent=4)
    except Exception as e:
        messagebox.showerror("Error", f"Failed to save addresses: {e}")

def open_settings():
    #Function managing the settings menu

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
            save_data(addresses)
            refresh_address_list()
        else:
            messagebox.showinfo("Incomplete", "All fields are required.")

    def delete_address():
        selected = address_listbox.curselection()
        if selected:
            index = selected[0]
            del addresses[index]
            save_data(addresses)
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
            save_data(addresses)  # Save the last selected address

    address_listbox.bind("<ButtonRelease-1>", on_address_click)

    tk.Button(settings_window, text="Add Address", command=add_address).pack(pady=5)
    tk.Button(settings_window, text="Delete Address", command=delete_address).pack(pady=5)

    refresh_address_list()

def change_username():
    global USERNAME
    new_username = simpledialog.askstring("Change Username", "Enter your username:", initialvalue=USERNAME)
    if new_username:
        if '|' in new_username or '.' in new_username:
            messagebox.showerror("Invalid Username", "Username cannot contain '|' or '.'. Please choose a different username.")
        else:
            USERNAME = new_username
            save_data(addresses)  # Save updated username to JSON
            print(f"Username updated to: {USERNAME}")
    elif new_username == "":
        messagebox.showinfo("Invalid Input", "Username cannot be empty.")
    else:
        print("Closed")

# Initialize the main window
root = tk.Tk()
root.title("Online Notepad")

# Create the text widget
text_widget = tk.Text(root, wrap=tk.WORD, undo=True)
text_widget.pack(fill=tk.BOTH, expand=True)

# Create the users list box
users_listbox = tk.Listbox(root, height=5, width=100)
users_listbox.pack(pady=10)

# Main Menu setup
menu_bar = tk.Menu(root)
file_menu = tk.Menu(menu_bar, tearoff=0)
file_menu.add_command(label="Open", command=open_file)
file_menu.add_command(label="Refresh", command=refresh_file)
menu_bar.add_cascade(label="File", menu=file_menu)

# Settings menu
settings_menu = tk.Menu(menu_bar, tearoff=0)
settings_menu.add_command(label="Manage Addresses", command=open_settings)
settings_menu.add_command(label="Change Username", command=change_username)
settings_menu.add_command(label="Connect to Address", command=start_tcp_connection, state=tk.DISABLED)  # Initially disabled until file is opened
menu_bar.add_cascade(label="Online Settings", menu=settings_menu)

root.config(menu=menu_bar)

#call the function that checks recieved messages after 100ms
root.after(100, process_server_messages)

# Track changes and save automatically
text_widget.bind("<KeyRelease>", lambda e: (save_file_content(), print_change(e)))
text_widget.bind("<ButtonRelease>", print_change)

# Load saved addresses
addresses = load_save_data()

# Closing protocol setup
root.protocol("WM_DELETE_WINDOW", lambda: (stop_tcp_connection(), root.destroy()))

# Start the application 
root.mainloop()