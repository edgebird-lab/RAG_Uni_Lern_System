# Graph traversal

## Breadth-first search

Breadth-first search (BFS) explores a graph level by level starting at a source vertex. It uses a queue: the source is enqueued first, and in every step the vertex at the front is removed and all its unvisited neighbours are marked as visited and enqueued. In an unweighted graph, BFS finds shortest paths measured in the number of edges. With adjacency lists its running time is O(V + E), where V is the number of vertices and E the number of edges.

## Depth-first search

Depth-first search (DFS) follows one path as deep as possible before backtracking. It can be implemented recursively or with an explicit stack and also runs in O(V + E) time. DFS is the basis for detecting cycles, computing topological orders of directed acyclic graphs and finding strongly connected components. If an edge leads to a vertex that is currently on the recursion stack, the directed graph contains a cycle.

## Dijkstra's algorithm

Dijkstra's algorithm computes shortest paths from a source vertex to all other vertices in a graph with non-negative edge weights. It keeps tentative distances in a priority queue, repeatedly extracts the vertex with the smallest distance, finalises its distance and updates the distances of its neighbours (relaxation). With a binary heap the running time is O((V + E) log V). The algorithm fails for negative edge weights; then the Bellman-Ford algorithm with running time O(V · E) is used instead.
