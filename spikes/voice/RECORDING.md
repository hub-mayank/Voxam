# Recording the 7 WER clips (Mayank, your own voice, your consent)

Audio stays on your Mac: `spikes/voice/data/` is gitignored, nothing is uploaded. The script reads these files and compares the speech-to-text output with the exact text below.

## Steps
1. Quiet room, built-in mic about 20 cm away, no music.
2. QuickTime Player -> File -> New Audio Recording (or the Voice Memos app).
3. Read ONE prompt below at your normal speed, with natural pauses. Do not re-read to make it perfect; a small stumble is useful. Stop recording. About 15-30 seconds each.
4. Save/export as `.m4a` with the exact filename `c01.m4a` ... `c07.m4a` into `spikes/voice/data/clips/` (in the voice worktree).
5. Tell the assistant when they are in. It converts them (`afconvert -f WAVE -d LEI16@16000 -c 1`) and runs `python spikes/voice/bench_wer.py`.

Limitation: these are read aloud, so the reference text is exact but the speech is more careful than a real viva answer.

| File | Read this aloud |
|---|---|
| c01 | A hash table stores key value pairs. A hash function turns the key into an index into an array. When two keys land on the same index we have a collision, which we can handle with chaining or open addressing. Lookups are constant time on average, and we resize the table when the load factor gets high. |
| c02 | Big O notation describes how the running time of an algorithm grows as the input size grows. It ignores constant factors and lower order terms, so it lets us compare algorithms fairly. For example, binary search takes logarithmic time, while a simple scan of a list takes linear time. |
| c03 | A database index is a data structure, usually a B tree, that lets the database find rows without scanning the whole table. It makes reads faster, but it uses extra storage and slows down writes, because every insert and update must also update the index. So we index the columns that queries filter on most often. |
| c04 | When you type a URL into a browser, the browser first asks DNS to find the server address. Then it opens a TCP connection and does a TLS handshake. After that it sends an HTTP request, receives the response, and finally renders the page. Caching can skip several of these steps. |
| c05 | A process has its own memory space, while threads inside a process share memory. Switching between threads is cheaper than switching between processes. But shared memory means threads can have race conditions, so we need locks, and processes give better isolation when one of them crashes. |
| c06 (Hinglish) | Hash table ek data structure hai jisme hum key ko hash function se ek index mein convert karte hain. Agar do keys same index par aa jaayein toh collision hota hai, jise hum chaining ya open addressing se handle karte hain. Average case mein lookup bahut fast hota hai, matlab constant time. |
| c07 (Hinglish) | Database mein index lagane se queries tez ho jaati hain, kyunki database poori table scan nahi karta. Lekin iska ek trade off hai: insert aur update thode slow ho jaate hain, aur extra storage bhi lagta hai. Isliye hum sirf wahi columns index karte hain jo queries mein bahut use hote hain. |
