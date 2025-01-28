import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog
import json
import threading
import queue
import socket
import time

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
            initial_message = initial_message + '\0'
            sock.sendall(initial_message.encode())

            # Synchronisation with master copy of the file
            line_count_data = sock.recv(BUFFER_SIZE).decode()
            line_count = int(line_count_data.strip())
            print(f"Server's master copy has {line_count} lines.")

            # Clear and replace the content of the text_widget
            content = ""
            for _ in range(line_count):
                line = sock.recv(BUFFER_SIZE).decode()
                line = line + '\0'
                sock.sendall(line.encode())
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
                    change = change + '\0'
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

        # Extract the number (1, 2, 4) to determine the action type
        try:
            message_type = int(message_parts[0])

        except ValueError:
            continue  # If it cannot be parsed, skip it

        # Switch case [Older Python's don't have implicit switch so bellow is a makeshift] behavior based on the first part (the message type)
        if message_type == 1:
            print("Handling message type 1: Text update")
            handle_text_update(message_parts[1:])

        elif message_type == 2:
            print("Handling message type 2: New user")
            users_handler(message_parts[1])

        elif message_type == 4:
            sync_count = int(message_parts[1])
            print("Handling message type 4: Server resynchronisation")
            file_synchro(sync_count)

        else:
            print(f"Unknown message type: {message_type}")

    # Schedule the function to run again
    root.after(100, process_server_messages)

def file_synchro(sync_count):
    sync_lines = []
    start_time = time.time()  # Record the start time for timeout handling
   
    try:
        # Disable the text widget to prevent user input during synchronization
        text_widget.config(state=tk.DISABLED)
        print("Text widget disabled during synchronization.")

        # Collect synchronization lines
        collected = 0
        while collected < sync_count:
            if time.time() - start_time > 1:  # Check for timeout
                print("Error: Synchronization timed out.")
                messagebox.showerror("Synchronization Error", "Synchronization timed out.")
                return

            if not from_server_queue.empty():
                # Get the next message from the queue
                line = from_server_queue.get()
                
                # Split lines in case the server sent multiple lines in one package
                for partial_line in line.splitlines():
                    if collected < sync_count:
                        sync_lines.append(partial_line.strip())
                        collected += 1
                    else:
                        print("Extra line received, ignoring:", partial_line)
            else:
                time.sleep(0.01)  # Small sleep within synchro is fine since synchro is already blocking

        if collected < sync_count:
            print("Error: Insufficient lines received during synchronization.")
            messagebox.showerror("Synchronization Error", "Not enough lines received.")
            return
        
        # Combine lines into file content
        new_content = "\n".join(sync_lines)

        # Update the text_widget with the synchronized content
        text_widget.config(state=tk.NORMAL)
        text_widget.delete("1.0", tk.END)
        text_widget.insert("1.0", new_content)

        print("Synchronization complete. Local copy updated.")
    except Exception as e:
        messagebox.showerror("Synchronization Error", f"Failed to update local copy: {e}")
        print(f"Error during synchronization: {e}")
        
    finally:
        # Re-enable the text widget
        text_widget.config(state=tk.NORMAL)
        print("Text widget re-enabled.")

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

        if X1 == X2:
            text_widget.delete(f"{X1}.{0}",f"{X1}.end")
            text_widget.insert(f"{X1}.0",text)
            print(f"The line {X1} is now: '{text}'")
        else:
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

def update_position_on_click(text_widget):
    global PREV_CURSOR_POSITION
    current_cursor_position = text_widget.index(tk.INSERT)
    PREV_CURSOR_POSITION = current_cursor_position

def print_change(event=None):
    global PREV_CURSOR_POSITION, START_CURSOR_POSITION

    current_cursor_position = text_widget.index(tk.INSERT)

    if event:
        # Handle directional key presses
        
        if event.keysym in ("Left", "Right", "Up", "Down"):
            PREV_CURSOR_POSITION = current_cursor_position
            return
        elif event.type == tk.EventType.ButtonPress:
            text_widget.after(1, lambda: update_position_on_click(text_widget))
            return
        

    # If the cursor has moved from the start of the change, update the start position
    if PREV_CURSOR_POSITION != current_cursor_position:
        if event:
            START_CURSOR_POSITION = PREV_CURSOR_POSITION

        # Capture the full range from start to current position
        left_position = START_CURSOR_POSITION
        right_position = current_cursor_position

        # Ensure the left position is earlier
        if left_position > right_position:
            left_position, right_position = right_position, left_position

        start_line, start_col = map(int, left_position.split('.'))
        end_line, end_col = map(int, right_position.split('.'))

        # Initialize text_range to capture all changes
        text_range = ""

        if start_line == end_line:
            # If it's on the same line
            line_start = f"{start_line}.0"
            line_end = f"{start_line + 1}.0"

            left_position = line_start  # Adjust left position to start of the line
            right_position = line_end  # Adjust right position to end of the line
            text_range = text_widget.get(line_start, line_end).rstrip()  # Get the entire line

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

        # Add the change to queue to be sent to the server
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
text_widget.bind("<Button-1>", print_change)

# Load saved addresses
addresses = load_save_data()

# Closing protocol setup
root.protocol("WM_DELETE_WINDOW", lambda: (stop_tcp_connection(), root.destroy()))

# Start the application 
root.mainloop()
