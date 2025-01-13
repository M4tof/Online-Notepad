import socket
import time

def simple_tcp_server(host='0.0.0.0', port=12345):
    try:
        server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_socket.bind((host, port))
        server_socket.listen(5)
        print(f"Server listening on {host}:{port}")
    except Exception as e:
        print(f"Error starting server: {e}")
        return

    try:
        while True:
            client_socket, client_address = server_socket.accept()
            print(f"Connection established with {client_address}")

            try:
                
                while True:
                    # Read data from the client
                    data = client_socket.recv(1024)
                    if not data:
                        break  # If no data is received, the connection is closed
                    print(f"Received: {data.decode('utf-8')}")
                    user = data.decode('utf-8').split('|')[1]

                    # Send "20" to the client as a first response
                    client_socket.sendall(b"20\n")
                    print("sent 20")

                    # Then send 20 lines "line 1", "line 2", ..., "line 20"
                    for i in range(1, 21):
                        line_message = f"line {i}\n"
                        client_socket.sendall(line_message.encode())
                        print("sent line: ",i)

                    time.sleep(1)
                    print("That part start")

                    sync_count = 10  # Start with 10 lines
                    while True:
                        # Send the synchronization header
                        sync_header = f"4.{sync_count}\n"
                        client_socket.sendall(sync_header.encode())
                        print(f"Sent: {sync_header.strip()}")

                        # Send the lines for the current synchronization
                        for i in range(1, sync_count + 1):
                            line_message = f"line{i}\n"
                            client_socket.sendall(line_message.encode())
                            print(f"Sent: {line_message.strip()}")

                        # Decrease the sync_count until it reaches 1
                        if sync_count > 1:
                            sync_count -= 1
                        else:
                            # If sync_count is 1, only send "4.1" and "line1" repeatedly
                            line_message = "line1\n"
                            client_socket.sendall(line_message.encode())
                            print(f"Sent: {line_message.strip()}")

                        time.sleep(2)

            except Exception as e:
                print(f"Error handling client {client_address}: {e}")

            finally:
                client_socket.close()
                print(f"Connection with {client_address} closed")

    except Exception as e:
        print(f"Error during server operation: {e}")

    finally:
        server_socket.close()
        print("Server shut down.")

if __name__ == "__main__":
    simple_tcp_server()
