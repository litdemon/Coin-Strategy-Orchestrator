


class Counter:
    def __init__(self):
        self.count_dict = {}

    def increment(self, key, num=1):
        if key not in self.count_dict:
            self.count_dict[key] = 0
        self.count_dict[key] += num

    def decrement(self, key, num=1):
        if key not in self.count_dict:
            self.count_dict[key] = 0
        self.count_dict[key] -= num

    def get_count(self, key:str = ''):
        if key == '':
            return sum(self.count_dict.values())
        return self.count_dict.get(key, 0)