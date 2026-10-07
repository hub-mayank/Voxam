"""Texts for the spike. STUDENT_TURNS are voiced with macOS `say` (en_IN voices) as stand-in speech: clean, so STT numbers on them
are optimistic and are always labelled synthetic. AI_SENTENCES are what the interviewer says (TTS tests)."""

STUDENT_TURNS = [
    # very short (idk / yes / no): common in a viva
    "I don't know.",
    "Yes, that is correct.",
    "I think it is the second option.",
    "Sorry, could you repeat the question?",
    "No idea, I have not used that before.",
    # short
    "A hash table maps keys to values using a hash function.",
    "Big O describes how running time grows with the input size.",
    "An index makes reads faster but writes slower.",
    "A thread shares memory with the other threads in the same process.",
    "DNS translates the domain name into an IP address.",
    "I built a chat application using websockets and a Postgres database.",
    "The main problem was that queries became slow when the table grew large.",
    # medium
    "When two keys end up at the same index we get a collision, and we can handle it with chaining or with open addressing.",
    "Binary search halves the search space at every step, so it takes logarithmic time, while a linear scan has to look at every element.",
    "A database index is usually a B tree, and it lets the database jump to the matching rows instead of scanning the whole table.",
    "In my project I used a queue to decouple the web server from the image processing workers so that uploads never blocked.",
    "I would first check the logs and metrics, then see whether the slowness is in the database, the application, or the network.",
    "The browser asks DNS for the address, opens a TCP connection, does the TLS handshake, sends the request and finally renders the response.",
    "Processes have separate memory so one crash does not affect the others, but threads are cheaper to create and to switch between.",
    "I chose chaining because it is simple to implement, and the load factor only affects how long the chains become on average.",
    "To scale reads I would add a cache in front of the database and use read replicas, and for writes I would shard by user identifier.",
    "The trade off is memory against speed: an index uses extra storage and every insert must update it, but lookups become much faster.",
    # long (about 25-30 s)
    "For the URL shortener I would generate a short identifier by encoding an auto incrementing number in base sixty two, store the mapping in a key value store, "
    "and put a cache in front so that the redirect path stays very fast even when the traffic is heavy.",
    "When the API became slow I first reproduced the problem with a load test, then looked at the database query plans and found a missing index on a column "
    "that was used in a filter, and after adding it the response time dropped from ten seconds to under two hundred milliseconds.",
    "A race condition happens when two threads read and write shared data without proper synchronisation, so the final result depends on the order in which they run, "
    "and we fix it with locks, atomic operations, or by avoiding shared mutable state altogether.",
    "In the project I worked on, we had a recommendation service that was calling the database for every request, so I introduced a caching layer with a time to live, "
    "measured the hit rate, and tuned the expiry so that the data stayed reasonably fresh while the database load dropped by more than half.",
    "I understand that consistency and availability pull in different directions during a network partition, so for the payments service we chose consistency "
    "and accepted that some requests would fail, while for the product catalogue we chose availability and allowed slightly stale data.",
    # extra mixed to reach 36
    "It depends on the access pattern, if we mostly read then a cache helps a lot.",
    "I would use a hash map here, because the lookups are frequent and the order does not matter.",
    "The complexity is linear because we visit each node exactly once.",
    "Honestly I am not sure, but I think we could use a tree instead.",
    "We deployed the service in containers and used health checks so that failing instances were replaced automatically.",
    "The first version worked on my laptop, but under load the connection pool was exhausted, so I limited the concurrency and added retries with backoff.",
    "Because the table is sorted we can use binary search and avoid the full scan.",
]

AI_SENTENCES = [
    "Can you explain how a hash table works?",
    "Good. What edge cases or trade-offs would you worry about here?",
    "You're partway there. Think about what happens as the input grows.",
    "Let's bring it back to the question. Could you answer that directly?",
    "Okay, let's move on.",
    "What is the difference between a process and a thread?",
    "What happens between typing a URL in a browser and seeing the page?",
    "What is an index in a database and what is the trade-off of adding one?",
    "Your API was fast yesterday and today responses take ten seconds. Walk me through how you would find the cause.",
    "You need to build a URL shortener. How would you design it?",
    "Is there anything you'd like to add? Thank you, that's the end of the viva.",
    "Thanks. Now tell me about a project you built and the hardest technical decision you had to make in it.",
    "That is a reasonable start. How would the design change if the traffic grew by a factor of one hundred?",
    "Why did you choose that approach instead of the alternatives?",
    "Describe a bug that took you a long time to find, and how you finally found it.",
    "What would you measure first to be sure the change actually helped?",
]
