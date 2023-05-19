from mpi4py import MPI

class TERMCOLORS:
    BLUE = '\033[94m',
    CYAN = '\033[96m',
    GREEN = '\033[92m',
    WARNING = '\033[93m',

comm = MPI.COMM_WORLD
rank = comm.Get_rank()

print(f"Rank {rank}")
