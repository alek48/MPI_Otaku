from mpi4py import MPI
from enum import IntEnum
import time

class TERMCOLORS:
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    WARNING = '\033[93m'

COLORS = {0: TERMCOLORS.BLUE, 1: TERMCOLORS.CYAN, 2: TERMCOLORS.GREEN, 3: TERMCOLORS.WARNING}

class STATES(IntEnum):
    REST = 1
    WAIT = 2
    INSECTION = 3
    PAUSE = 4
    REPLACING = 5

class TAGS(IntEnum):
    REQ = 1
    ACK = 2
    RELEASE = 3
    EMPTY = 4
    RESUME = 5

clock : int = 0

class Message:
    def __init__(self, tag : TAGS, data : str):
        global clock
        self.tag : int = tag
        self.data : str = data
        self.clock : int = clock

CURRENT_STATE = STATES.PAUSE

comm = MPI.COMM_WORLD
rank = comm.Get_rank()
status = MPI.Status()

def send(tag, dest, data=""):
    global clock, comm
    comm.send(Message(tag, data), dest)
    clock += 1

def multisend(tag, dest, data=""):
    global clock, comm
    for d in dest:
        comm.send(Message(tag, data), d)
    clock += 1

def broadcast(tag, data=""):
    global clock, comm
    for i in range(comm.Get_size()):
        if i != rank:
            comm.send(Message(tag, data), i)
    clock += 1

def receive() -> Message:
    global clock, status
    msg : Message = comm.recv()
    clock += 1
    return msg

def debug(msg):
    global clock, rank
    print(f"{COLORS[rank % 3]}[{rank}][{clock}] {msg}")

def onReceivePause(msg : Message):
    debug(f"Received: tag={msg.tag} msg={msg.data}")


def main():
    while True:
        debug("Waiting for recv")
        data = receive()

        if CURRENT_STATE == STATES.REST:
            pass
        elif CURRENT_STATE == STATES.WAIT:
            pass
        elif CURRENT_STATE == STATES.INSECTION:
            pass
        elif CURRENT_STATE == STATES.PAUSE:
            onReceivePause(data)
        elif CURRENT_STATE == STATES.REPLACING:
            pass
        else:
            debug("Invalid state")

        time.sleep(2)

    
        # send("ACK", 1, "asdfrt")

if rank == 0:
    broadcast(TAGS.ACK, "Test msg")
else:
    main()