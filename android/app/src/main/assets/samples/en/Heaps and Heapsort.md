# Heaps and Heapsort

## Heap property

A binary heap is a complete binary tree in which every node satisfies the heap property. In a max-heap the key of each node is greater than or equal to the keys of its children, so the largest key is always stored at the root. In a min-heap the order is reversed: the root holds the smallest key. Because the tree is complete, it can be stored compactly in an array: the children of the node at index i are located at indices 2i+1 and 2i+2, and its parent is located at index (i-1)/2 (rounded down).

## Operations

When inserting, the new element is first appended at the end of the array, which keeps the tree complete. Then it is moved upwards by swapping it with its parent as long as it violates the heap property (sift-up). That takes at most O(log n) swaps, because a complete binary tree with n nodes has a height of about log2(n).

When removing the maximum, the root is replaced by the last element of the array, the heap shrinks by one, and the new root is moved downwards (sift-down): it is always swapped with the larger of its two children until the heap property holds again. This also costs O(log n).

## Building a heap and heapsort

A heap can be built from an unsorted array in O(n) time by calling sift-down on all inner nodes, from the last inner node up to the root. Heapsort first builds a max-heap and then repeatedly swaps the root with the last element of the heap region, shrinks the heap and restores the heap property. Its running time is O(n log n) in the best, average and worst case. Heapsort sorts in place, but it is not stable.

## Priority queues

A priority queue is an abstract data type that supports inserting elements with a priority and extracting the element with the highest priority. A binary heap implements both operations in O(log n). Applications are Dijkstra's algorithm, event-driven simulation and operating system schedulers.
