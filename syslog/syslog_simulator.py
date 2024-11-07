import socket
import time
import os

# Get the target host and port from environment variables
syslog_host = os.getenv('SYSLOG_HOST', 'rsyslog')
syslog_port = int(os.getenv('SYSLOG_PORT', 514))

# Create a UDP socket
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

# Generate and send syslog messages every few seconds
while True:
    message = "<34>1 - MySyslogSimulator - - - Test syslog message"
    sock.sendto(message.encode(), (syslog_host, syslog_port))
    print(f"Sent syslog message to {syslog_host}:{syslog_port}")
    time.sleep(5)  # Send a message every 5 seconds
