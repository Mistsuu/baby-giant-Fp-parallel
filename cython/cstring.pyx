from libc.string cimport memcmp as cmemcmp

def memcmp(char[:] arr1, char[:] arr2, l, r):
    return cmemcmp(&arr1[l], &arr2[l], r-l)

def memswap(char[:] arr1, char[:] arr2, n):
    cdef char tmp
    for i in range(n):
        tmp     = arr1[i]
        arr1[i] = arr2[i]
        arr2[i] = tmp