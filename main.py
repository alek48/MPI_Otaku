from typing import Any, List
from mpi4py import MPI
from enum import IntEnum
from random import random
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

def GetTag(num):
    for key, member in TAGS.__members__.items():
        if member.value == num:
            return key
    raise ValueError("Value not found in enum")

clock : int = 0

comm = MPI.COMM_WORLD
rank = comm.Get_rank()

class Message:
    def __init__(self, tag : TAGS, data : Any):
        global clock, rank
        self.tag : int = tag
        self.data : Any = data
        self.clock : int = clock
        self.sender : int = rank

    def __str__(self):
        return f"Message=(tag={GetTag(self.tag)}, data={self.data} clock={self.clock} sender={self.sender})"

class QueueMember:
    def __init__(self, rank : int, clock : int, gas : int):
        self.rank = rank
        self.clock = clock
        self.gas = gas

    def __str__(self):
        return f"Member=(rank={self.rank} clock={self.clock} gas={self.gas})"

PREVIOUS_STATE = STATES.REST
CURRENT_STATE = STATES.REST

def changeState(newState):
    global PREVIOUS_STATE, CURRENT_STATE
    PREVIOUS_STATE = CURRENT_STATE
    CURRENT_STATE = newState

messageFreezer : List[Message] = []
RoomGas : int = 0
InhaledGas : int = 0
WaitQueue : List[QueueMember] = []
LastResume : int = 0
EmptyNum : int = 0
AckNum: int = 0
SelfGas: int = 0
S: int = 1  # ilość stanowisk w sali
X: int = 10  # ilość cuchów, po której trzeba wymienić reprezentanta
M: int = 5  # maksymalne dozwolone stężenie cuchów na sali

def addToQueue(rank, clock, gas):
    global WaitQueue
    WaitQueue.append( QueueMember(rank, clock, gas) )
    WaitQueue = sorted(WaitQueue, key=lambda x : x.clock)
    # sortowane po zegarze, bo w takiej kolejności wpuszczamy do sali

def removeFromQueue(rank):
    global WaitQueue
    WaitQueue = [x for x in WaitQueue if x.rank != rank]

def send(tag, dest, data=None):
    global clock, comm
    comm.send(Message(tag, data), dest)
    clock += 1

def multisend(tag, dest, data=None):
    global clock, comm
    for d in dest:
        comm.send(Message(tag, data), d)
    clock += 1

def broadcast(tag, data=None, self=False):
    global clock, comm
    for i in range(comm.Get_size()):
        if self or i != rank:
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
    global RoomGas, InhaledGas, LastResume, EmptyNum

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

def onReceiveReplacing(msg : Message):
    global RoomGas, InhaledGas, LastResume, EmptyNum

    # REQ - Przechowuje wiadomość, żeby obsłużyć ją po opuszczeniu tego stanu.
    if (msg.tag == TAGS.REQ):
        messageFreezer.append(msg)
    
    # ACK - Ignoruje; sytuacja niemożliwa.
    elif (msg.tag == TAGS.ACK):
        pass
    
    # RELEASE - Usuwa nadawcę z WaitQueue, aktualizuje RoomGas oraz InhaledGas (opisane poniżej).
    elif (msg.tag == TAGS.RELEASE):
        removeFromQueue(msg.sender)
        # TODO: update gas
    
    # EMPTY - Zwiększa EmptyNum o 1.
    elif (msg.tag == TAGS.EMPTY):
        EmptyNum += 1
    
    # RESUME - przechodzi do stanu REST, ustawia LastResume na zegar Lamporta tej wiadomości i ustawia InhaledGas na 0.
    elif (msg.tag == TAGS.RESUME):
        changeState(STATES.REST)
        LastResume = msg.clock
        InhaledGas = 0


def onReceiveRest(msg: Message):
    # REQ - dodaj nadawcę do kolejki i odeślj ACK
    if (msg.tag == TAGS.REQ):
        addToQueue(msg.sender, msg.clock, msg.data)
        updateRoomGas()
        send(TAGS.ACK, msg.sender)

    # ACK - sytuacja niemożliwa
    elif (msg.tag == TAGS.ACK):
        pass

    # RELEASE - usuń nadawcę z kolejki, zaktualizuj RoomGas oraz InhaledGas
    elif (msg.tag == TAGS.RELEASE):
        removeFromQueue(msg.sender)
        # TODO: aktualizuj gaz

    # EMPTY - sytuacja niemożliwa
    elif msg.tag == TAGS.EMPTY:
        pass

    # RESUME - sytuacja niemożliwa
    elif msg.tag == TAGS.RESUME:
        pass

def onReceiveWait(msg: Message):
    global AckNum
    if (msg.tag == TAGS.REQ):
        addToQueue(msg.sender,msg.clock, msg.data)
        updateRoomGas()
        send(TAGS.ACK, msg.sender)

    # ACK - zwiększ licznik Ack o 1
    elif (msg.tag == TAGS.ACK):
        AckNum += 1

    # RELEASE - usuń nadawcę z kolejki, zaktualizuj RoomGas oraz InhaledGas
    elif (msg.tag == TAGS.RELEASE):
        removeFromQueue(msg.sender)
        # TODO: aktualizuj gaz

    # EMPTY - sytuacja niemożliwa
    elif msg.tag == TAGS.EMPTY:
        pass
    # RESUME - sytuacja niemożliwa
    elif msg.tag == TAGS.RESUME:
        pass

def onReceiveInsection(msg: Message):
    if (msg.tag == TAGS.REQ):
        addToQueue(msg.sender, msg.clock, msg.data)
        updateRoomGas()
        send(TAGS.ACK, msg.sender)

    # ACK - sytuacja niemożliwa
    elif (msg.tag == TAGS.ACK):
        pass

    # RELEASE - usuń nadawcę z kolejki, zaktualizuj RoomGas oraz InhaledGas
    elif (msg.tag == TAGS.RELEASE):
        removeFromQueue(msg.sender)
        # TODO: aktualizuj gaz

    # EMPTY - sytuacja niemożliwa
    elif msg.tag == TAGS.EMPTY:
        pass
    # RESUME - sytuacja niemożliwa
    elif msg.tag == TAGS.RESUME:
        pass

def updateRoomGas():
    global RoomGas

    i = 0
    RoomGas = 0

    for process in WaitQueue:
        RoomGas += process.gas

        i += 1
        if i > S:
            break

def updateInhaledGas(msg : Message):
    global InhaledGas, LastResume, rank

    # InhaledGas jest zwiększane o OwnGas procesu wysyłającego RELEASE pod warunkiem, że zegar Lamporta RELEASE jest większy
    #  niż zegar Lamporta ostatniego otrzymanego RESUME (LastResume).
    if msg.clock > LastResume:
        InhaledGas += msg.data

    # Jeżeli przedstawiciel zemdleje (InhaledGas > X), to proces:
    # Wysyła RELEASE jeśli jest INSECTION, następnie przechodzi do PAUSE, jeśli nie był nadawcą RELEASE.
    if InhaledGas > X:
       if CURRENT_STATE == STATES.INSECTION:
           broadcast(TAGS.RELEASE, self=True) 

           if rank == msg.sender:
               changeState(STATES.REPLACING)
           else:
               changeState(STATES.PAUSE)
    # Przechodzi do REPLACING, jeśli był nadawcą RELEASE.

def joinQueue():
    global comm, rank, clock, SelfGas, AckNum
    debug("I'm sitting in queue")
    broadcast(TAGS.REQ, SelfGas)
    addToQueue(rank, clock, SelfGas)
    changeState(STATES.WAIT)
    AckNum = 0


def main():
    global comm, SelfGas, rank, clock, AckNum, RoomGas

    # Initialize
    SelfGas = round(random() * 100)
    time.sleep(random() * 10)

    if (random() > 0.667):
        joinQueue()

    while True:
        msg = receive()
        debug(f"Received {msg}")

        if CURRENT_STATE == STATES.REST:
            onReceiveWait(msg)
            if random() > 0.667:
                joinQueue()

        elif CURRENT_STATE == STATES.WAIT:
            onReceiveWait(msg)
            if (AckNum >= comm.Get_size() - 1):
                if (rank in [x.rank for x in WaitQueue[:S]]):
                    if (RoomGas + SelfGas < M):
                        changeState(STATES.INSECTION)
                        debug("I'm entering the room")
                    else:
                        debug("Can't join - Gas")
                else:
                    debug("Can't join - Rank")
            else:
                debug("Can't join - AckNum")
            # if (AckNum >= comm.Get_size() - 1) and (rank in [x.rank for x in WaitQueue[:S]]) and (
            #         RoomGas + SelfGas < M):
                changeState(STATES.INSECTION)
                debug("I'm entering the room")

        elif CURRENT_STATE == STATES.INSECTION:
            onReceiveInsection(msg)
            time.sleep(4)
            broadcast(TAGS.RELEASE, SelfGas)
            removeFromQueue(rank)
            updateInhaledGas(Message(TAGS.RELEASE, SelfGas))
            changeState(STATES.REST)
            debug("I'm back")

        elif CURRENT_STATE == STATES.PAUSE:
            onReceivePause(msg)

        elif CURRENT_STATE == STATES.REPLACING:
            onReceiveReplacing(msg)

            # Proces i przebywa w stanie REPLACING dopóki nie otrzyma EMPTY od wszystkich innych procesów, 
            # wtedy rozsyła on RESUME do wszystkich procesów, wliczając siebie.
            if EmptyNum + 1 == comm.Get_size():
                broadcast(TAGS.RESUME, self=True)

        else:
            debug("Invalid state")

main()