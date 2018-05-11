#!/usr/bin/env python
import os
import filecmp

pathToRef = os.getcwd() + '/referenceOutput_of-ccx/'
pathToOutput = os.getcwd() + '/Output_of-ccx/'

fileListRef = os.listdir(pathToRef)
fileListOutput = os.listdir(pathToOutput)

fileListRef.sort()
fileListOutput.sort()

def comparison():
    for x, y in zip(fileListRef, fileListOutput):
        if not filecmp.cmp(pathToRef + x, pathToOutput + y):
            raise Exception('Output differs from reference')

if __name__ == "__main__":
    comparison()
