import redis

redis_db = redis.Redis(host='127.0.0.1',port=6379, db=0)

redis_db.set('test', 5.0)

print(float(redis_db.get('test1')))