from typing import Any, List
from mpi4py import MPI
from enum import IntEnum
from random import random
from time import sleep

DEBUG_TO_FILE = False
DEBUG_ENABLED = False

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
SelfGas: int = 1
r: int = 0
S: int = 3  # ilość stanowisk w sali
X: int = 30  # ilość cuchów, po której trzeba wymienić reprezentanta
M: int = 20  # maksymalne dozwolone stężenie cuchów na sali

def addToQueue(rank, clock, gas):
    global WaitQueue
    WaitQueue.append( QueueMember(rank, clock, gas) )
    WaitQueue = sorted(WaitQueue, key=lambda x : (x.clock, x.rank))
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
    global clock, comm, messageFreezer
    for i in range(comm.Get_size()):
        if i != rank:
            comm.send(Message(tag, data), i)
    if self:
        messageFreezer.append(Message(tag, data))
    clock += 1

def receive() -> Message:
    global clock, status
    msg : Message = comm.recv()
    clock = max(clock+1, msg.clock)
    return msg

def debug(msg):
    if DEBUG_ENABLED:
        info("[D!] " + msg)

def info(msg):
    global clock, rank
    print(f"{COLORS[rank % 3]}[{rank}][{clock}] {msg}", flush=True)
    if DEBUG_TO_FILE:
        with open(f'{rank}log.txt', 'a') as f:
            f.write(f'{rank}|{clock}|{msg}\n')


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
        messageFreezer.append(msg)

    # EMPTY - Ignoruje; sytuacja niemożliwa.
    elif (msg.tag == TAGS.EMPTY):
        pass

    # RESUME - Wraca do stanu poprzedniego (lub REST, jeśli wcześniej był INSECTION), ustawia LastResume na zegar Lamporta tej wiadomości i ustawia InhaledGas na 0.
    elif (msg.tag == TAGS.RESUME):
        info('Wracam z pauzy')
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
        messageFreezer.append(msg)
    
    # RELEASE - Usuwa nadawcę z WaitQueue, aktualizuje RoomGas oraz InhaledGas (opisane poniżej).
    elif (msg.tag == TAGS.RELEASE):
        messageFreezer.append(msg)

    
    # EMPTY - Zwiększa EmptyNum o 1.
    elif (msg.tag == TAGS.EMPTY):
        EmptyNum += 1
    
    # RESUME - przechodzi do stanu REST, ustawia LastResume na zegar Lamporta tej wiadomości i ustawia InhaledGas na 0.
    elif (msg.tag == TAGS.RESUME):
        pass


def onReceiveRest(msg: Message):
    global EmptyNum
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
        updateRoomGas()
        updateInhaledGas(msg)

    # EMPTY - sytuacja niemożliwa
    elif msg.tag == TAGS.EMPTY:
        EmptyNum += 1
    # RESUME - sytuacja niemożliwa
    elif msg.tag == TAGS.RESUME:
        pass

def onReceiveWait(msg: Message):
    global AckNum, EmptyNum
    if (msg.tag == TAGS.REQ):
        addToQueue(msg.sender, msg.clock, msg.data)
        updateRoomGas()
        send(TAGS.ACK, msg.sender)

    # ACK - zwiększ licznik Ack o 1
    elif (msg.tag == TAGS.ACK):
        AckNum += 1

    # RELEASE - usuń nadawcę z kolejki, zaktualizuj RoomGas oraz InhaledGas
    elif (msg.tag == TAGS.RELEASE):
        removeFromQueue(msg.sender)
        updateRoomGas()
        updateInhaledGas(msg)

    # EMPTY - sytuacja niemożliwa
    elif msg.tag == TAGS.EMPTY:
        EmptyNum += 1
    # RESUME - sytuacja niemożliwa
    elif msg.tag == TAGS.RESUME:
        pass

def onReceiveInsection(msg: Message):
    global EmptyNum
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
        updateRoomGas()
        updateInhaledGas(msg)

    # EMPTY - sytuacja niemożliwa
    elif msg.tag == TAGS.EMPTY:
        EmptyNum += 1
    # RESUME - sytuacja niemożliwa
    elif msg.tag == TAGS.RESUME:
        pass

def updateRoomGas():
    global RoomGas

    RoomGas = 0
    i = 0
    for process in WaitQueue[:S]:
        if RoomGas + process.gas > M:
            break
        RoomGas += process.gas
        i += 1
    return i

def updateInhaledGas(msg : Message):
    global InhaledGas, LastResume, rank
    # InhaledGas jest zwiększane o OwnGas procesu wysyłającego RELEASE pod warunkiem, że zegar Lamporta RELEASE jest większy
    #  niż zegar Lamporta ostatniego otrzymanego RESUME (LastResume).
    if msg.clock > LastResume:
        InhaledGas += msg.data
    # Jeżeli przedstawiciel zemdleje (InhaledGas > X), to proces:
    # Wysyła RELEASE jeśli jest INSECTION, następnie przechodzi do PAUSE, jeśli nie był nadawcą RELEASE.
    if InhaledGas > X:
        InhaledGas = 0
        if CURRENT_STATE == STATES.INSECTION:
            changeState(STATES.REST)
            broadcast(TAGS.RELEASE, SelfGas)
            removeFromQueue(rank)
        if rank == r:
            changeState(STATES.REPLACING)
            info("Wymieniam przedstawiciela")
            return
        changeState(STATES.PAUSE)
        info(f'Przedstawiciel umarł przez [{msg.sender}]. Pauzuje działanie i wychodze z sali')
        send(TAGS.EMPTY, 0)


def joinQueue():
    global comm, rank, clock, SelfGas, AckNum
    info("Ide stać w kolejce")
    addToQueue(rank, clock, SelfGas)
    AckNum = 0
    broadcast(TAGS.REQ, SelfGas)
    changeState(STATES.WAIT)

def ReceiveMessage():
    global comm, SelfGas, rank, clock, AckNum, RoomGas, messageFreezer, EmptyNum, LastResume, EmptyNum, InhaledGas

    if CURRENT_STATE in (STATES.REST, STATES.INSECTION, STATES.WAIT) and len(messageFreezer):
        msg = messageFreezer.pop(0)
    else:
        msg = receive()
    
    debug(f"Otrzymałem {msg}")

    if CURRENT_STATE == STATES.REST:
        onReceiveRest(msg)

    elif CURRENT_STATE == STATES.WAIT:
        onReceiveWait(msg)
        if (CURRENT_STATE != STATES.WAIT): return

        if (AckNum >= comm.Get_size() - 1):
            amountInRoom = updateRoomGas()
            if (rank in [x.rank for x in WaitQueue[:amountInRoom]]):
                changeState(STATES.INSECTION)
                info("Wchodzę na salę")
            else:
                debug(f"Can't join - am={amountInRoom} RG={RoomGas} SG={SelfGas} M={M}, wq={[x.__str__() for x in WaitQueue]}")
        else:
            debug(f"Can't join - AckNum={AckNum} < {comm.Get_size() - 1}")

    elif CURRENT_STATE == STATES.INSECTION:
        onReceiveInsection(msg)

    elif CURRENT_STATE == STATES.PAUSE:
        onReceivePause(msg)

    elif CURRENT_STATE == STATES.REPLACING:
        onReceiveReplacing(msg)

        # Proces i przebywa w stanie REPLACING dopóki nie otrzyma EMPTY od wszystkich innych procesów, 
        # wtedy rozsyła on RESUME do wszystkich procesów, wliczając siebie.
        if EmptyNum + 1 == comm.Get_size():
            EmptyNum = 0
            LastResume = msg.clock
            InhaledGas = 0
            broadcast(TAGS.RESUME)
            info('Wymieniłem reprezentanta. Wracam z pauzy')
            changeState(PREVIOUS_STATE)

    else:
        debug("Invalid state")


def main():
    global SelfGas, comm, rank

    if DEBUG_TO_FILE:
        with open(f'{rank}log.txt', 'w') as f:
            f.write('')

    SelfGas = max(1, round(random() * 10))
    info(f"Budzę się z SelfGas={SelfGas}")

    while True:
        received = comm.Iprobe() or (len(messageFreezer) and CURRENT_STATE in (STATES.REST, STATES.WAIT, STATES.INSECTION))

        if received:
            ReceiveMessage()
        else:
            # do stuff while waiting for message
            if CURRENT_STATE == STATES.REST and (not (rank in (x.rank for x in WaitQueue))) and random()>0.5:
                sleep(2*random())
                joinQueue()
            elif CURRENT_STATE == STATES.INSECTION and random() > 0.5:
                sleep(2*random())

                changeState(STATES.REST)
                broadcast(TAGS.RELEASE, SelfGas, self=True)
                info("Wychodzę z sali")


main()
