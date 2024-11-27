# client.py
import threading
import queue
import socket
import time
import tkinter as tk
from PIL import Image, ImageTk
import json
import logging
import uuid

# Configure logging
logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)

# Configuration and credential file paths
SERVER_CONFIG_FILE = "client_config.json"
CLIENT_CREDENTIALS_FILE = "credentials.json"
CLIENT_LOGO = "client_logo.png"
CLIENT_UUID = str(uuid.uuid4())  # Generate a UUID for this client

# Load server configurations
try:
    with open(SERVER_CONFIG_FILE, 'r') as f:
        SERVERS = json.load(f)
except FileNotFoundError:
    logger.error(f"Error: Server configuration file '{SERVER_CONFIG_FILE}' not found.")
    exit(1)
except json.JSONDecodeError:
    logger.error(f"Error: Invalid JSON in server configuration file.")
    exit(1)

# Load client credentials
try:
    with open(CLIENT_CREDENTIALS_FILE, 'r') as f:
        CLIENT_CREDENTIALS = json.load(f)
except FileNotFoundError:
    logger.error(f"Error: Client credentials file '{CLIENT_CREDENTIALS_FILE}' not found.")
    exit(1)
except json.JSONDecodeError:
    logger.error(f"Error: Invalid JSON in client credentials file.")
    exit(1)

# Global variables
tokens = {}
auth_success_count = 0
actions_performed_count = 0
log_queue = queue.Queue()
udp_port = 5005  # Port for UDP communication
broadcast_address = '255.255.255.255' # Broadcast address

# UDP Socket
client_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
client_socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
client_socket.bind(('', udp_port))  # Bind to the specified port for receiving responses
client_socket.settimeout(0.5)

def log_message(message):
    log_queue.put(message)

def authenticate(server_name, server_address, username, password):
    global auth_success_count
    request_id = str(uuid.uuid4())
    request = {
        'type': 'login',
        'username': username,
        'password': password,
        'client_id': CLIENT_UUID,
        'request_id': request_id,
        'server_name': server_name
    }
    try:
        client_socket.sendto(json.dumps(request).encode(), (broadcast_address, udp_port))
        start_time = time.time()
        while time.time() - start_time < 5:
            try:
                data, addr = client_socket.recvfrom(1024)
                response = json.loads(data.decode())
                if response.get('request_id') == request_id and response.get('server_name') == server_name:
                    if 'token' in response:
                        token = response['token']
                        tokens[server_name + username] = token
                        auth_success_count += 1
                        log_message(f"SUCCESS: Authenticated {username} with {server_name}.")
                        return token
                    elif 'error' in response:
                        log_message(f"ERROR: {server_name}: Authentication failed for {username}: {response['error']}")
                        return None
            except socket.timeout:
                continue
            except json.JSONDecodeError:
                logger.warning("Received non-JSON data or malformed JSON data.")
                continue
        log_message(f"ERROR: {server_name}: Authentication timeout for {username}.")
        return None
    except OSError as e:
        log_message(f"ERROR: {server_name}: Authentication failed for {username}, Socket Error : {e}")
        return None



def perform_action(server_name, username, token):
    global actions_performed_count
    request_id = str(uuid.uuid4())
    request = {
        'type': 'action',
        'token': token,
        'client_id': CLIENT_UUID,
        'request_id': request_id,
        'server_name': server_name
    }
    try:
        client_socket.sendto(json.dumps(request).encode(), (broadcast_address, udp_port))
        start_time = time.time()
        while time.time() - start_time < 5:
            try:
                data, addr = client_socket.recvfrom(1024)
                response = json.loads(data.decode())
                if response.get('request_id') == request_id and response.get('server_name') == server_name:
                    if 'message' in response:
                        actions_performed_count += 1
                        log_message(f"SUCCESS: Performed action on {server_name} as {username}.")
                        return
                    elif 'error' in response:
                        log_message(f"ERROR: {server_name}: Action failed for {username}: {response['error']}")
                        return
            except socket.timeout:
                continue
            except json.JSONDecodeError:
                logger.warning("Received non-JSON data or malformed JSON data.")
                continue
        log_message(f"ERROR: {server_name}: Action timeout for {username}.")
    except OSError as e:
        log_message(f"ERROR: {server_name}: Action failed for {username}, Socket error {e}")



def simulate_client_activity():
    for server_name, server_address in SERVERS.items():
        for creds in CLIENT_CREDENTIALS:
            token = authenticate(server_name, server_address, creds['username'], creds['password'])
            if token:
                perform_action(server_name, creds['username'], token)
            time.sleep(1)

class ClientGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Client Application Dashboard")

        try:
            self.original_image = Image.open(CLIENT_LOGO)
            screen_width = root.winfo_screenwidth()
            screen_height = root.winfo_screenheight()
            image_width, image_height = self.original_image.size

            if image_width > screen_width or image_height > screen_height:
                if image_width / screen_width > image_height / screen_height:
                    new_width = screen_width
                    new_height = int(image_height * (screen_width / image_width))
                else:
                    new_height = screen_height
                    new_width = int(image_width * (screen_height / image_height))
            else:
                new_width, new_height = image_width, image_height

            self.resized_image = self.original_image.resize((new_width, new_height), Image.LANCZOS)
            self.photo = ImageTk.PhotoImage(self.resized_image)
            self.image_label = tk.Label(root, image=self.photo)
            self.image_label.pack()
        except FileNotFoundError:
            logger.error(f"Image file not found: {CLIENT_LOGO}")

        self.auth_label = tk.Label(root, text="Successful Authentications: 0", font=("Helvetica", 14))
        self.auth_label.pack()

        self.action_label = tk.Label(root, text="Actions Performed: 0", font=("Helvetica", 14))
        self.action_label.pack()

        self.log_text = tk.Text(root, height=10, state='disabled', wrap=tk.WORD)
        self.log_text.pack(fill=tk.BOTH, expand=True)

        self.update_gui()

    def update_gui(self):
        while not log_queue.empty():
            message = log_queue.get()
            self.log_message(message)

        self.auth_label.config(text=f"Successful Authentications: {auth_success_count}")
        self.action_label.config(text=f"Actions Performed: {actions_performed_count}")
        self.root.after(1000, self.update_gui)

    def log_message(self, message):
        self.log_text.config(state='normal')
        self.log_text.insert(tk.END, message + "\n")
        self.log_text.see(tk.END)
        self.log_text.config(state='disabled')



def main():
    client_thread = threading.Thread(target=simulate_client_activity, daemon=True)
    client_thread.start()

    root = tk.Tk()
    gui = ClientGUI(root)
    root.mainloop()

if __name__ == '__main__':
    main()
