class HashTable:
    #custom hash table for caching user sessions
    def __init__(self, size=500):
        self.size = size
        self.table = [[] for _ in range(size)]
        self.item_count = 0
    
    def _hash(self, key):
        #hash function using polynomial rolling hash
        hash_value = 0
        for i, char in enumerate(str(key)):
            hash_value += ord(char) * (31 ** i)
        return hash_value % self.size
    
    def insert(self, key, value):
        #insert or update key value pair
        hash_index = self._hash(key)
        bucket = self.table[hash_index]
        
        #check if key exists, update if it does
        for i, (k, v) in enumerate(bucket):
            if k == key:
                bucket[i] = (key, value)
                return True
        
        #if key doesn't exist, append new entry
        bucket.append((key, value))
        self.item_count += 1
        return True
    
    def get(self, key):
        #get value by key
        hash_index = self._hash(key)
        bucket = self.table[hash_index]
        
        for k, v in bucket:
            if k == key:
                return v
        return None
    
    def delete(self, key):
        #remove key value pair
        hash_index = self._hash(key)
        bucket = self.table[hash_index]
        
        for i, (k, v) in enumerate(bucket):
            if k == key:
                del bucket[i]
                self.item_count -= 1
                return True
        return False
    
    def clear(self):
        #clear all entries from hash table
        self.table = [[] for _ in range(self.size)]
        self.item_count = 0
    
    def get_stats(self):
        #get statistics about hash table performance
        non_empty_buckets = sum(1 for bucket in self.table if bucket)
        max_bucket_size = max(len(bucket) for bucket in self.table)
        avg_bucket_size = self.item_count / non_empty_buckets if non_empty_buckets > 0 else 0
        
        return {
            'total_items': self.item_count,
            'table_size': self.size,
            'non_empty_buckets': non_empty_buckets,
            'max_bucket_size': max_bucket_size,
            'avg_bucket_size': round(avg_bucket_size, 2),
            'load_factor': round(self.item_count / self.size, 2)
        }
    
    def __len__(self):
        return self.item_count
    
    def __contains__(self, key):
        return self.get(key) is not None

#global session cache
user_session_cache = HashTable(size=500)

#test function to verify hash table is working
def test_hash_table():
    print("Testing Hash Table")
    test_cache = HashTable(size=10)
    
    #test insertion
    print("Testing insertion...")
    test_cache.insert("user1@test.com", 1)
    test_cache.insert("user2@test.com", 2)
    test_cache.insert("user3@test.com", 3)
    
    #test retrieval
    print("Testing retrieval...")
    assert test_cache.get("user1@test.com") == 1, "Failed to retrieve user1"
    assert test_cache.get("user2@test.com") == 2, "Failed to retrieve user2"
    assert test_cache.get("user3@test.com") == 3, "Failed to retrieve user3"
    print("Retrieval works correctly")
    
    #test update
    print("Testing update...")
    test_cache.insert("user1@test.com", 100)
    assert test_cache.get("user1@test.com") == 100, "Failed to update user1"
    print("Update works correctly")
    
    #test deletion
    print("Testing deletion...")
    assert test_cache.delete("user2@test.com") == True, "Failed to delete user2"
    assert test_cache.get("user2@test.com") == None, "user2 still exists after deletion"
    print("Deletion works correctly")
    
    #test collision handling
    print("Testing collision handling...")
    #force collisions by using small hash table
    for i in range(20):
        test_cache.insert(f"user{i}@test.com", i)
    
    #verify all values can still be retrieved
    for i in range(20):
        if i != 2:  #user2 was deleted
            value = test_cache.get(f"user{i}@test.com")
            assert value == i, f"Failed to retrieve user{i} after collisions"
    print("✓ Collision handling works correctly")
    
    #test statistics
    print("Testing statistics...")
    stats = test_cache.get_stats()
    print(f"Total items: {stats['total_items']}")
    print(f"Load factor: {stats['load_factor']}")
    print(f"Max bucket size: {stats['max_bucket_size']}")
    print(f"Avg bucket size: {stats['avg_bucket_size']}")
    
    #test clear
    print("Testing clear...")
    test_cache.clear()
    assert len(test_cache) == 0, "Failed to clear hash table"
    assert test_cache.get("user1@test.com") == None, "Items still exist after clear"
    print("Clear works correctly")
    
    print("All hash table tests passed!\n")

#run tests if this file is executed directly
if __name__ == "__main__":
    test_hash_table()
