# Baby Step Giant Step for Elliptic Curves in F_p Parallelized

## Introduction
One day, I was doing a CTF Challenge about elliptic curve and realize that the solution requires finding discrete log of a particular point in GF(p) where p is a 100-bit number. 

Luckily, the order of the point is just a 48-bit number, which means it is still somewhat feasible doing a babystep-giantstep. However, when I tried to solve using sage's `discrete_log()`, the program blew up and ate all of my computer's RAM, including the swap memory.
*(Later, another player who I know has plenty more RAM than mine, said that the program actually took 30GBs...)*

And to be honest, I believe it was an intentional move made by the organizers, to push the players in realizing that the problem could be solved by a different method that is way smarter and less space consuming than just plain-old babygiant stuffs :) Which sucks, because I didn't know that until I'd solved it, while giving birth to a program that is as tighted-space as possible, utilising as many cores as possible, to solve the problem.
*(In the end, it took only 1GB and 10 minutes to solve with 4 cores so yey :>)*