import threading
import queue
import uuid
import hashlib
import time
import logging
import json
import socket
import tkinter as tk
from PIL import Image, ImageTk

# Configuration
CONFIG_FILE = "server_config.json"

try:
    with open(CONFIG_FILE, "r") as f:
        config = json.load(f)
except FileNotFoundError:
    print(f"Error: Configuration file '{CONFIG_FILE}' not found.")
    exit(1)

# Extract configuration values
BUILDING_NAME = config.get("building_name", "Generic Institution")
BUILDING_LOGO = config.get("building_logo", "institution_logo.png")
VALID_CREDENTIALS = config.get("credentials", {})
SERVER_PORT = config.get("port", 80)  # Not used in UDP version
TOKEN_EXPIRY = config.get("token_expiry", 3600)  # Default: 1 hour

# Configure logging
logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Token storage (hashed tokens with expiry times)
valid_tokens = {}

# Queue for logging and GUI updates
gui_queue = queue.Queue()

# UDP Socket
udp_port = 5005  # Port for UDP communication
broadcast_address = '255.255.255.255'  # Define broadcast address here
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)  # Enable broadcasting
sock.bind(('', udp_port))
sock.settimeout(1)

# Function to send messages to the GUI queue
def send_gui_message(message_type, message):
    gui_queue.put({"type": message_type, "content": message})

def process_udp_requests():
    while True:
        try:
            data, addr = sock.recvfrom(1024)
            request = json.loads(data.decode())
            request_id = request.get('request_id')
            server_name = request.get('server_name')

            if request['type'] == 'login':
                username = request['username']
                password = request['password']

                if username in VALID_CREDENTIALS and VALID_CREDENTIALS[username] == password:
                    token = str(uuid.uuid4())
                    hashed_token = hashlib.sha256(token.encode()).hexdigest()
                    valid_tokens[hashed_token] = (username, time.time() + TOKEN_EXPIRY, request.get('client_id'))
                    response = {'token': token, 'request_id': request_id, 'server_name': server_name}
                    sock.sendto(json.dumps(response).encode(), (addr[0], udp_port))  # Send directly to client
                    logger.info(f"SUCCESS: {username} logged in from {addr[0]}:{addr[1]}.")
                    send_gui_message("log", f"SUCCESS: {username} logged in from {addr[0]}:{addr[1]}.")
                else:
                    response = {'error': 'Invalid credentials', 'request_id': request_id, 'server_name': server_name}
                    sock.sendto(json.dumps(response).encode(), (addr[0], udp_port))
                    logger.warning(f"FAILURE: Invalid login attempt for username: {username} from {addr[0]}:{addr[1]}.")
                    send_gui_message("log", f"FAILURE: Invalid login attempt for {username} from {addr[0]}:{addr[1]}.")

            elif request['type'] == 'action':
                token = request.get('token')
                hashed_token = hashlib.sha256(token.encode()).hexdigest()
                if hashed_token in valid_tokens:
                    username, expiry_time, client_id = valid_tokens[hashed_token]
                    if client_id == request.get('client_id') and time.time() <= expiry_time:
                        logger.info(f"ACTION: {username} performed an action from {addr[0]}:{addr[1]}.")
                        send_gui_message("log", f"ACTION: {username} performed an action from {addr[0]}:{addr[1]}.")
                        response = {'message': f'Action performed for {username}', 'request_id': request_id, 'server_name': server_name}
                        sock.sendto(json.dumps(response).encode(), (addr[0], udp_port))  # Send directly to client

                    else:
                        response = {'error': 'Token expired or invalid client', 'request_id': request_id, 'server_name': server_name}
                        sock.sendto(json.dumps(response).encode(), (addr[0], udp_port))
                        logger.warning(f"UNAUTHORIZED: Invalid token or client ID attempt from {addr[0]}:{addr[1]}.")

                        if time.time() > expiry_time:
                            del valid_tokens[hashed_token]
                else:
                     response = {'error': 'Unauthorized', 'request_id': request_id, 'server_name': server_name}
                     sock.sendto(json.dumps(response).encode(), (addr[0], udp_port))
                     logger.warning(f"UNAUTHORIZED: Invalid token attempt from {addr[0]}:{addr[1]}.")

        except socket.timeout:
            pass  # No data received within timeout
        except json.JSONDecodeError:
            logger.warning("Received non-JSON data or malformed JSON data.")

class ServerGUI:
    def __init__(self, root):
        self.root = root
        self.root.title(f"{BUILDING_NAME} Server Dashboard")

        try:
            self.original_image = Image.open(BUILDING_LOGO)  # Keep original image

            # Get screen dimensions
            screen_width = root.winfo_screenwidth()
            screen_height = root.winfo_screenheight()

            # Calculate new image dimensions while maintaining aspect ratio
            image_width, image_height = self.original_image.size
            if image_width > screen_width or image_height > screen_height:
                if image_width / screen_width > image_height / screen_height:
                    # Width is the limiting factor
                    new_width = screen_width
                    new_height = int(image_height * (screen_width / image_width))
                else:
                    # Height is the limiting factor
                    new_height = screen_height
                    new_width = int(image_width * (screen_height / image_height))
            else:
                new_width, new_height = image_width, image_height  # No resize needed

            self.resized_image = self.original_image.resize((new_width, new_height), Image.LANCZOS) # High-quality resize
            self.photo = ImageTk.PhotoImage(self.resized_image)
            self.image_label = tk.Label(root, image=self.photo)
            self.image_label.pack()
        except FileNotFoundError:
            logger.error(f"Image file not found: {BUILDING_LOGO}")
            send_gui_message("error", f"Image file not found: {BUILDING_LOGO}")

        self.clients_label = tk.Label(root, text="Connected Clients: 0", font=("Helvetica", 14))
        self.clients_label.pack()

        self.log_text = tk.Text(root, height=10, state='disabled')
        self.log_text.pack(fill=tk.BOTH, expand=True)

        self.error_label = tk.Label(root, text="", fg="red")  # For displaying errors
        self.error_label.pack()

        self.update_gui()



    def update_gui(self):
        # Check for expired tokens
        expired_tokens = [token for token, (username, expiry, client_id) in valid_tokens.items() if time.time() > expiry] # Fix: unpack client_id

        for token in expired_tokens:
            del valid_tokens[token]
            logger.info(f"Token for {username} expired")
            send_gui_message("log", f"Token for {username} expired")

        while not gui_queue.empty():
            message = gui_queue.get()

            if message["type"] == "log":
                self.log_message(message["content"])
            elif message["type"] == "error":
                self.show_error(message["content"])

        client_count = len(valid_tokens)
        self.clients_label.config(text=f"Connected Clients: {client_count}")
        self.root.after(1000, self.update_gui)  # Update every 1000ms (1 second)

    def log_message(self, message):
        self.log_text.config(state='normal')
        self.log_text.insert(tk.END, message + "\n")
        self.log_text.see(tk.END)
        self.log_text.config(state='disabled')

    def show_error(self, message):
        self.error_label.config(text=message)
        self.root.after(5000, lambda: self.error_label.config(text=""))  # Clear error after 5 seconds



def main():
    udp_thread = threading.Thread(target=process_udp_requests, daemon=True)
    udp_thread.start()

    root = tk.Tk()
    gui = ServerGUI(root)
    root.mainloop()

if __name__ == '__main__':
    main()