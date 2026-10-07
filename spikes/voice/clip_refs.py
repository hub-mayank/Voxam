"""Reference texts for the 7 clips Mayank records (see RECORDING.md; the text there and here must stay identical)."""

HINGLISH = {"c06", "c07"}

REFS = {
    "c01": (
        "A hash table stores key value pairs. A hash function turns the key into an index into an array. When two keys "
        "land on the same index we have a collision, which we can handle with chaining or open addressing. Lookups are "
        "constant time on average, and we resize the table when the load factor gets high."
    ),
    "c02": (
        "Big O notation describes how the running time of an algorithm grows as the input size grows. It ignores "
        "constant factors and lower order terms, so it lets us compare algorithms fairly. For example, binary search "
        "takes logarithmic time, while a simple scan of a list takes linear time."
    ),
    "c03": (
        "A database index is a data structure, usually a B tree, that lets the database find rows without scanning the "
        "whole table. It makes reads faster, but it uses extra storage and slows down writes, because every insert and "
        "update must also update the index. So we index the columns that queries filter on most often."
    ),
    "c04": (
        "When you type a URL into a browser, the browser first asks DNS to find the server address. Then it opens a TCP "
        "connection and does a TLS handshake. After that it sends an HTTP request, receives the response, and finally "
        "renders the page. Caching can skip several of these steps."
    ),
    "c05": (
        "A process has its own memory space, while threads inside a process share memory. Switching between threads is "
        "cheaper than switching between processes. But shared memory means threads can have race conditions, so we need "
        "locks, and processes give better isolation when one of them crashes."
    ),
    "c06": (
        "Hash table ek data structure hai jisme hum key ko hash function se ek index mein convert karte hain. Agar do "
        "keys same index par aa jaayein toh collision hota hai, jise hum chaining ya open addressing se handle karte "
        "hain. Average case mein lookup bahut fast hota hai, matlab constant time."
    ),
    "c07": (
        "Database mein index lagane se queries tez ho jaati hain, kyunki database poori table scan nahi karta. Lekin "
        "iska ek trade off hai: insert aur update thode slow ho jaate hain, aur extra storage bhi lagta hai. Isliye hum "
        "sirf wahi columns index karte hain jo queries mein bahut use hote hain."
    ),
}
