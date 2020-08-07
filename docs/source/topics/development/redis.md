# Redis

## Resetting the redis queue

On the server:

```
    docker exec -ti broker  /bin/bash
    redis-cli
    FLUSHALL
    exit
    exit

    docker restart websecmap-worker-storage
    docker restart websecmap-worker-reporting
```
