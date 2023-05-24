from typing import List
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
    ACK = 1
    REQ = 2
    RELEASE = 3
    EMPTY = 4
    RESUME = 5

clock : int = 0

comm = MPI.COMM_WORLD
rank = comm.Get_rank()

class Message:
    def __init__(self, tag : TAGS, data : str):
        global clock, rank
        self.tag : int = tag
        self.data : str = data
        self.clock : int = clock
        self.sender : int = rank

    def __str__(self):
        return f"Message=(tag={self.tag}, data={self.data} clock={self.clock} sender={self.sender})"

class QueueMember:
    def __init__(self, rank : int, clock : int, gas : int):
        self.rank = rank
        self.clock = clock
        self.gas = gas

    def __str__(self):
        return f"Member=(rank={self.rank} clock={self.clock} gas={self.gas})"

PREVIOUS_STATE = STATES.REST
CURRENT_STATE = STATES.PAUSE

def changeState(newState):
    global PREVIOUS_STATE, CURRENT_STATE
    PREVIOUS_STATE = CURRENT_STATE
    CURRENT_STATE = newState

messageFreezer : List[Message] = []
RoomGas : int = 0
InhaledGas : int = 0
WaitQueue : List[QueueMember] = []
LastResume : int = 0

def addToQueue(rank, clock, gas):
    global WaitQueue
    WaitQueue.append( QueueMember(rank, clock, gas) )
    WaitQueue = sorted(WaitQueue, key=lambda x : x.gas)

def removeFromQueue(rank):
    global WaitQueue
    WaitQueue = [x for x in WaitQueue if x.rank != rank]

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
    global RoomGas, InhaledGas, LastResume

    debug(f"Received: {msg}")
    
    # REQ - Przechowuje wiadomość, żeby obsłużyć ją po opuszczeniu tego stanu (opisane poniżej).
    if (msg.tag == TAGS.REQ):
        messageFreezer.append(msg)

    # ACK - Przechowuje wiadomość, żeby obsłużyć ją po opuszczeniu tego stanu.
    elif (msg.tag == TAGS.ACK):
        messageFreezer.append(msg)

    # RELEASE - Usuwa nadawcę z WaitQueue, aktualizuje RoomGas oraz InhaledGas (opisane poniżej).
    elif (msg.tag == TAGS.RELEASE):
        removeFromQueue(msg.sender)
        # TODO: update gas

    # EMPTY - Ignoruje; sytuacja niemożliwa.
    elif (msg.tag == TAGS.EMPTY):
        pass

    # RESUME - Wraca do stanu poprzedniego (lub REST, jeśli wcześniej był INSECTION), ustawia LastResume na zegar Lamporta tej wiadomości i ustawia InhaledGas na 0.
    elif (msg.tag == TAGS.RESUME):
        if PREVIOUS_STATE == STATES.INSECTION:
            changeState(STATES.REST)
        else:
            changeState(PREVIOUS_STATE)

        LastResume = msg.clock

        InhaledGas = 0




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

if rank == 0:
    broadcast(TAGS.ACK, "Test msg")
else:
    main()