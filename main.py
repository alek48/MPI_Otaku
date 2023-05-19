from mpi4py import MPI
from enum import Enum

class TERMCOLORS:
    BLUE = '\033[94m',
    CYAN = '\033[96m',
    GREEN = '\033[92m',
    WARNING = '\033[93m',


STATES = Enum("STATES", ["REST", "WAIT", "INSECTION", "PAUSE", "REPLACING"])

clock = 0

comm = MPI.COMM_WORLD
rank = comm.Get_rank()

def embedClockWithMsg(data):
    global clock
    return {
        "clock": clock,
        "msg": data
    }

def send(tag, dest, msg=""):
    global clock, comm
    comm.send(msg, dest, tag)
    clock += 1

def multisend(tag, dest, msg=""):
    global clock, comm
    for d in dest:
        comm.send(msg, d, tag)
    clock += 1

def debug(msg):
    global clock, rank
    print(f"{TERMCOLORS.BLUE}[{rank}][{clock}] {msg}")

while True:
    debug("Waiting for recv")
    if not rank == 0:
        received = comm.recv()

        debug(f"Received={received}")

    if rank == 0:
        send("ACK", 1, "asdfrt")