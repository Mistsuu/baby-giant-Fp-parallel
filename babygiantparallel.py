from ast import Yield
from sage.all                   import *
from tqdm                       import tqdm
from multiprocessing            import Process, Queue
from multiprocessing.managers   import SharedMemoryManager
from collections                import deque


# ----------------------------------------------------------------------------------
# -                 Building memcmp & memswap if not exist yet.
# ----------------------------------------------------------------------------------

import sys
import os
def buildCythonModules():
    pythonPath = sys.executable
    os.system(f"\"{pythonPath}\" cython/setupCython.py build_ext --build-lib cython/ --build-temp cython/")

try:
    sys.path.append("cython/")
    from cstring import memcmp, memswap

except ModuleNotFoundError as err:
    print("[*] Module \"cstring\" is not built yet! Let me take a moment to build it, please :)")
    buildCythonModules()
    print("[*] Module \"cstring\" is built!")

    from cstring import memcmp, memswap

# ----------------------------------------------------------------------------------

def buildLRArray(
    L, R, 
    X, Y,
    n, p,
    ncores
):  
    # Size of the arrays for baby-step giant-step
    indexSize = n.bit_length() // 8 + 1
    itemSize  = p.bit_length() // 8 + 1

    # Indices to help access view.
    r = indexSize
    s = indexSize+itemSize

    # Get item size
    nPerCore = n // ncores
    nLstCore = n - nPerCore * (ncores - 1)

    # Build variables
    k    =  nPerCore
    kX   =  k * X
    nkX  =  n * kX
    _nX  = -n * X

    def _buildLRArray(L, R, _L, _R, off, n):
        # Get memoryview from the object to modify
        viewL = L.buf[off*s:off*s+n*s]
        viewR = R.buf[off*s:off*s+n*s]

        # Update L-R list
        for _ in range(off, off+n):
            # Update view
            viewL[:r]  = _         .to_bytes(indexSize, 'little')
            viewL[r:s] = int(_L[0]).to_bytes(itemSize,  'little')
            viewR[:r]  = viewL[:r]
            viewR[r:s] = int(_R[0]).to_bytes(itemSize,  'little')
            # Update value & shift view
            _L    += X
            _R    += _nX
            viewL  = viewL[s:]
            viewR  = viewR[s:]

    # Create processes
    futures = []
    for i in range(ncores):
        if i != ncores - 1:
            futures.append(Process(
                            target=_buildLRArray,
                            args=(
                                L, R, 
                                i*kX, Y-i*nkX, 
                                i*k, nPerCore, 
                            )))
        else:
            futures.append(Process(
                            target=_buildLRArray,
                            args=(
                                L, R, 
                                i*kX, Y-i*nkX, 
                                i*k, nLstCore, 
                            )))

    # Start all processes
    for future in futures:
        future.start()

    # Wait for all of them to finish :)
    for future in futures:
        future.join()


def sortLRArray(sharedMem, n: int, p: int, ncores):

    #################### PART 1: INITIALIZING VARIABLES AND FUNCTIONS ########################
    # Size of the arrays for baby-step giant-step
    indexSize = n.bit_length() // 8 + 1
    itemSize  = p.bit_length() // 8 + 1
    fieldSize = indexSize+itemSize

    def _partition(view: memoryview, lo: int, hi: int):
        i     = lo
        pivot = view[ hi*fieldSize : ]

        subviewI = view[ lo*fieldSize : ]
        subviewJ = view[ lo*fieldSize : ]
        for j in range(lo, hi):
            # Swap if element is less than pivot
            if memcmp(subviewJ, pivot, indexSize, fieldSize) <= 0:
                memswap(subviewI, subviewJ, fieldSize)
                # Update view i
                subviewI = subviewI[fieldSize:]
                i += 1
            # Update view j
            subviewJ = subviewJ[fieldSize:]
        # Swap i with pivot 
        memswap(subviewI, pivot, fieldSize)
        return i

    def _quicksort(sharedMem, lo: int, hi: int):
        # Get memoryview from shared memory :)
        view = sharedMem.buf

        # Recursively sort
        sortQueue = deque()
        sortQueue.append((lo, hi))
        while sortQueue:
            # Pop current lookup indices
            lo, hi = sortQueue.pop()

            # Get partition index
            pi = _partition(view, lo, hi)

            # Append lookup indices to quicksort queue
            if lo < pi-1:
                sortQueue.append((lo, pi-1))
            if pi+1 < hi:
                sortQueue.append((pi+1, hi))

    
    #################### PART 2: CREATE <ncores> SORTED PARTS OF ARRAY ########################
    # Get array length for each core to process
    nPerCore = n // ncores

    # Create processes
    futures = []
    for i in range(ncores):
        if i != ncores - 1:
            futures.append(Process(
                            target=_quicksort, 
                            args=(sharedMem, i*nPerCore, (i+1)*nPerCore-1)
                          ))
        else:
            futures.append(Process(
                            target=_quicksort, 
                            args=(sharedMem, i*nPerCore, n-1)
                          ))

    # Start all processes
    for future in futures:
        future.start()

    # Wait for all of them to finish :)
    for future in futures:
        future.join()


def searchLRArray(L, R, n: int, p: int, ncores):
    #################### PART 1: INITIALIZING VARIABLES AND FUNCTIONS ########################
    # Size of the arrays for baby-step giant-step
    indexSize = n.bit_length() // 8 + 1
    itemSize  = p.bit_length() // 8 + 1
    fieldSize = indexSize+itemSize

    # Finding values in partial views
    def _searchLRArray(L, R, lL, hL, lR, hR, retQueue):
        # Crop the views to correct size
        viewL = L.buf
        viewR = R.buf
        viewL = viewL[lL*fieldSize:hL*fieldSize]
        viewR = viewR[lR*fieldSize:hR*fieldSize]

        # Finding in views
        while True:
            # Update L-view
            while viewL.nbytes and memcmp(viewL, viewR, indexSize, fieldSize) < 0:
                viewL = viewL[fieldSize:]
            if not viewL.nbytes:
                return

            # Update R-view
            while viewR.nbytes and memcmp(viewR, viewL, indexSize, fieldSize) < 0:
                viewR = viewR[fieldSize:]
            if not viewR.nbytes:
                return

            # If same, yey
            if memcmp(viewL, viewR, indexSize, fieldSize) == 0:
                retQueue.put([
                    int.from_bytes(viewL[:indexSize], 'little'),
                    int.from_bytes(viewR[:indexSize], 'little'),
                ])
                return

    #################### PART 2: FINDING!!! ########################
    # Get array length for each core to process
    nPerCore = n // ncores
    nLstCore = n - nPerCore * (ncores - 1)

    # Hold return value
    retQueue = Queue()

    # Create processes
    for iL in range(ncores):
        # Create new processes
        futures = []
        for iR in range(ncores):
            # set lL, hL
            if iL != ncores - 1:
                lL = iL*nPerCore
                hL = (iL+1)*nPerCore
            else:
                lL = iL*nPerCore
                hL = n
            # set lR, hR
            if iR != ncores - 1:
                lR = iR*nPerCore
                hR = (iR+1)*nPerCore
            else:
                lR = iR*nPerCore
                hR = n
            # append to list of awaiting processes
            futures.append(Process(
                            target=_searchLRArray,
                            args=(
                                L, R, 
                                lL, hL, 
                                lR, hR,
                                retQueue, 
                            )))
        
        # Start all processes
        for future in futures:
            future.start()

        for future in futures:
            future.join()

    # Not hold the return values anymore :3
    lr = []
    while not retQueue.empty():
        lr.append(retQueue.get())
    return lr

def discrete_log_elliptic_curve_Fp(X, Y, ncores=4, debug=False):
    with SharedMemoryManager() as memManager:

        #################### PART 0: INITIALIZING ########################
        # Check if using more than 2 cores
        assert ncores >= 2, ValueError("1 core sucks :(")

        # n - the size of each L-R array; p - the size of field
        n = int(1 + isqrt(X.order()))
        p = int(X[0].parent().characteristic())
        assert is_prime(p), ValueError("Elliptic curve must be in prime field!")
        if debug: print(f"[*] Debug: n = {n}")
        if debug: print(f"[*] Debug: p = {p}")
        
        # Size of the arrays for baby-step giant-step
        indexSize = n.bit_length() // 8 + 1
        itemSize  = p.bit_length() // 8 + 1
        fieldSize = indexSize+itemSize

        #################### PART 1: GENERATE L&R ########################
        # Initialize arrays
        if debug: print(f'[*] Memory consumption (for baby-giant arrays): {2*fieldSize*n} bytes')
        L = memManager.SharedMemory(size=fieldSize*n)
        R = memManager.SharedMemory(size=fieldSize*n)

        # Generate L-R list for collision attack
        if debug: print(f'[*] Creating baby (L) and giant (R) arrays for collision attack :)')
        buildLRArray(
            L, R, 
            X, Y, 
            n, p,
            ncores
        )

        #################### PART 2: SORTING ########################
        # Sort L-R in ascending order - but with my way muhahha :)
        if debug: print(f'[*] Sorting L memory...')
        sortLRArray(L, n, p, ncores)
    
        if debug: print(f'[*] Sorting R memory...')
        sortLRArray(R, n, p, ncores)

        #################### PART 3: LOOKUP ########################
        # After <ncores> sublists of L-R is sorted, 
        # find the common element.
        if debug: print(f'[*] Search for elements with common X-coordinates in L-R...')
        lr = searchLRArray(L, R, n, p, ncores)

        #################### PART 4: GET IT!!! ########################
        # After <ncores> sublists of L-R is sorted, 
        # find the common point with similar X-coordinates.
        k = None
        for l, r in lr:
            # -- Case 1:  l*X = Y - r*n*X
            k = l + r*n
            if X*k == Y:
                break
            # -- Case 2: -l*X = Y - r*n*X
            k = (r*n - l) % int(X.order())
            if X*k == Y:
                break
        
        # Just return it...
        assert k != None, ValueError(f'Cannot find the discrete_log({Y}, base={X}')
        return k

if __name__ == '__main__':
    p = 0xa7926d93132516cc2d782df50f
    a = 0x19115c33b343d7176c634a53ab
    b = 0x0a335cf375ef2b2f833387ffde

    E = EllipticCurve(GF(p), [a, b])
    G = E(0xa0f60c10eb8fccb6e114ae3224, 0x72e5576f1eda71b7f782821838)
    Gorder = 0x30c2227a93e75

    x = randrange(2, Gorder)
    Gx = G*x

    print(f'{G = }')
    print(f'{x = }')
    print(f'{Gx = }')
    recoveredX = discrete_log_elliptic_curve_Fp(G, Gx, ncores=4, debug=True)
    print(f'{recoveredX = }')