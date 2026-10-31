"""Coding problems for technical mock interviews.

Each problem is a real interview-style task with a precise statement,
examples, constraints, starter code per language and test cases. The browser
runs the tests for Python (Pyodide), JavaScript (Web Worker) and SQL (sql.js);
nothing is executed on the server. Java and C++ answers are reviewed
statically.

Difficulty follows the candidate's level, as real interview loops do:

- entry (0-2 years): easy problems, occasionally medium
- mid (2-5 years): medium problems
- senior (5+ years): medium and hard problems

``reference`` is a correct Python solution. ``tests/test_question_quality.py``
runs it against every test case, so an answer key can never be wrong, and the
scorecard shows it as a model answer after the interview.
"""

from __future__ import annotations

import hashlib
from typing import Any

LEVEL_DIFFICULTIES = {
    "entry": ("easy", "easy", "medium"),
    "mid": ("medium", "medium", "easy", "hard"),
    "senior": ("medium", "hard", "hard"),
}
RUNNABLE_LANGUAGES = ("python", "javascript", "sql")


def _starter(name_py: str, params: str, name_js: str, java_sig: str, cpp_sig: str) -> dict[str, str]:
    return {
        "python": f"def {name_py}({params}):\n    # Write your solution here\n    pass\n",
        "javascript": f"function {name_js}({params}) {{\n  // Write your solution here\n}}\n",
        "java": f"class Solution {{\n    {java_sig} {{\n        // Write your solution here\n    }}\n}}\n",
        "cpp": f"{cpp_sig} {{\n    // Write your solution here\n}}\n",
    }


PROBLEMS: list[dict[str, Any]] = [
    {
        "id": "pair-with-target-sum", "title": "Pair with target sum", "difficulty": "easy", "topics": ("arrays", "hashing"),
        "statement": "Given a list of integers nums and an integer target, return the indexes [i, j] (i < j) of the two numbers that add up to target. Exactly one answer exists. Do not use the same element twice.",
        "examples": [{"input": "nums = [2, 7, 11, 15], target = 9", "output": "[0, 1]"}, {"input": "nums = [3, 2, 4], target = 6", "output": "[1, 2]"}],
        "constraints": ["2 <= len(nums) <= 10^5", "Aim for O(n) time"],
        "entry": {"python": "pair_with_sum", "javascript": "pairWithSum"},
        "starter": _starter("pair_with_sum", "nums, target", "pairWithSum", "public int[] pairWithSum(int[] nums, int target)", "std::vector<int> pairWithSum(std::vector<int>& nums, int target)"),
        "tests": [
            {"args": [[2, 7, 11, 15], 9], "expected": [0, 1]},
            {"args": [[3, 2, 4], 6], "expected": [1, 2]},
            {"args": [[3, 3], 6], "expected": [0, 1]},
            {"args": [[-4, 10, 1, 8], 4], "expected": [0, 3]},
        ],
        "signals": [r"\b(?:dict|set|map|Map|HashMap|unordered_map|seen|\{\})", r"\bfor\b|\bwhile\b|forEach|enumerate"],
        "complexity": "O(n) time and O(n) space with a hash map from value to index.",
        "reference": "def pair_with_sum(nums, target):\n    seen = {}\n    for i, x in enumerate(nums):\n        if target - x in seen:\n            return [seen[target - x], i]\n        seen[x] = i\n",
    },
    {
        "id": "valid-brackets", "title": "Balanced brackets", "difficulty": "easy", "topics": ("stack", "strings"),
        "statement": "Given a string s containing only the characters ()[]{}, return true if every bracket is closed by the same type of bracket in the correct order, otherwise false. An empty string is balanced.",
        "examples": [{"input": 's = "([]{})"', "output": "true"}, {"input": 's = "(]"', "output": "false"}],
        "constraints": ["0 <= len(s) <= 10^4"],
        "entry": {"python": "is_balanced", "javascript": "isBalanced"},
        "starter": _starter("is_balanced", "s", "isBalanced", "public boolean isBalanced(String s)", "bool isBalanced(const std::string& s)"),
        "tests": [
            {"args": ["([]{})"], "expected": True}, {"args": ["(]"], "expected": False}, {"args": [""], "expected": True},
            {"args": ["(("], "expected": False}, {"args": ["{[()()]}"], "expected": True}, {"args": ["())"], "expected": False},
        ],
        "signals": [r"\b(?:stack|append|push|pop|Stack|Deque|ArrayDeque)\b"],
        "complexity": "O(n) time and O(n) space with a stack of open brackets.",
        "reference": "def is_balanced(s):\n    pairs = {')': '(', ']': '[', '}': '{'}\n    stack = []\n    for ch in s:\n        if ch in pairs:\n            if not stack or stack.pop() != pairs[ch]:\n                return False\n        else:\n            stack.append(ch)\n    return not stack\n",
    },
    {
        "id": "first-unique-character", "title": "First non-repeating character", "difficulty": "easy", "topics": ("strings", "hashing"),
        "statement": "Given a string s of lowercase letters, return the index of the first character that appears exactly once. Return -1 if there is none.",
        "examples": [{"input": 's = "leetcode"', "output": "0"}, {"input": 's = "aabb"', "output": "-1"}],
        "constraints": ["1 <= len(s) <= 10^5"],
        "entry": {"python": "first_unique", "javascript": "firstUnique"},
        "starter": _starter("first_unique", "s", "firstUnique", "public int firstUnique(String s)", "int firstUnique(const std::string& s)"),
        "tests": [
            {"args": ["leetcode"], "expected": 0}, {"args": ["loveleetcode"], "expected": 2}, {"args": ["aabb"], "expected": -1},
            {"args": ["z"], "expected": 0}, {"args": ["abcabd"], "expected": 2},
        ],
        "signals": [r"\b(?:Counter|count|dict|map|Map|HashMap|\[26\]|freq)"],
        "complexity": "O(n) time: one pass to count, one pass to find the first count of 1.",
        "reference": "from collections import Counter\n\ndef first_unique(s):\n    counts = Counter(s)\n    for i, ch in enumerate(s):\n        if counts[ch] == 1:\n            return i\n    return -1\n",
    },
    {
        "id": "clean-palindrome", "title": "Palindrome after cleaning", "difficulty": "easy", "topics": ("strings", "two pointers"),
        "statement": "Return true if s reads the same forwards and backwards after removing every character that is not a letter or digit and ignoring case.",
        "examples": [{"input": 's = "A man, a plan, a canal: Panama"', "output": "true"}, {"input": 's = "race a car"', "output": "false"}],
        "constraints": ["0 <= len(s) <= 2 * 10^5", "Bonus: O(1) extra space with two pointers"],
        "entry": {"python": "is_clean_palindrome", "javascript": "isCleanPalindrome"},
        "starter": _starter("is_clean_palindrome", "s", "isCleanPalindrome", "public boolean isCleanPalindrome(String s)", "bool isCleanPalindrome(const std::string& s)"),
        "tests": [
            {"args": ["A man, a plan, a canal: Panama"], "expected": True}, {"args": ["race a car"], "expected": False},
            {"args": [""], "expected": True}, {"args": ["0P"], "expected": False}, {"args": ["No 'x' in Nixon"], "expected": True},
        ],
        "signals": [r"\b(?:isalnum|lower|toLowerCase|replace|isLetterOrDigit|left|right|\[::-1\])"],
        "complexity": "O(n) time; O(1) extra space with two pointers moving inwards.",
        "reference": "def is_clean_palindrome(s):\n    cleaned = [ch.lower() for ch in s if ch.isalnum()]\n    return cleaned == cleaned[::-1]\n",
    },
    {
        "id": "max-subarray", "title": "Maximum subarray sum", "difficulty": "easy", "topics": ("arrays", "dynamic programming"),
        "statement": "Given a non-empty list of integers, return the largest sum of any contiguous subarray (at least one element).",
        "examples": [{"input": "nums = [-2, 1, -3, 4, -1, 2, 1, -5, 4]", "output": "6", "explanation": "[4, -1, 2, 1] has sum 6"}],
        "constraints": ["1 <= len(nums) <= 10^5", "Aim for O(n) time (Kadane's algorithm)"],
        "entry": {"python": "max_subarray", "javascript": "maxSubarray"},
        "starter": _starter("max_subarray", "nums", "maxSubarray", "public int maxSubarray(int[] nums)", "int maxSubarray(std::vector<int>& nums)"),
        "tests": [
            {"args": [[-2, 1, -3, 4, -1, 2, 1, -5, 4]], "expected": 6}, {"args": [[1]], "expected": 1},
            {"args": [[-3, -1, -2]], "expected": -1}, {"args": [[5, 4, -1, 7, 8]], "expected": 23},
        ],
        "signals": [r"\bmax\b|Math\.max|std::max", r"\b(?:current|best|curr|running)\b"],
        "complexity": "O(n) time and O(1) space: keep the best sum ending here and the best overall.",
        "reference": "def max_subarray(nums):\n    best = current = nums[0]\n    for x in nums[1:]:\n        current = max(x, current + x)\n        best = max(best, current)\n    return best\n",
    },
    {
        "id": "dedupe-keep-order", "title": "Remove duplicates, keep first order", "difficulty": "easy", "topics": ("arrays", "hashing"),
        "statement": "Return a new list with duplicate values removed, keeping the first occurrence of each value in its original order.",
        "examples": [{"input": "items = [3, 1, 3, 2, 1]", "output": "[3, 1, 2]"}],
        "constraints": ["0 <= len(items) <= 10^5"],
        "entry": {"python": "dedupe", "javascript": "dedupe"},
        "starter": _starter("dedupe", "items", "dedupe", "public List<Integer> dedupe(List<Integer> items)", "std::vector<int> dedupe(const std::vector<int>& items)"),
        "tests": [
            {"args": [[3, 1, 3, 2, 1]], "expected": [3, 1, 2]}, {"args": [[]], "expected": []},
            {"args": [[7, 7, 7]], "expected": [7]}, {"args": [["b", "a", "b"]], "expected": ["b", "a"]},
        ],
        "signals": [r"\b(?:set|Set|seen|dict\.fromkeys|LinkedHashSet|unordered_set)\b"],
        "complexity": "O(n) time with a set of seen values.",
        "reference": "def dedupe(items):\n    return list(dict.fromkeys(items))\n",
    },
    {
        "id": "longest-unique-substring", "title": "Longest substring without repeats", "difficulty": "medium", "topics": ("strings", "sliding window"),
        "statement": "Given a string s, return the length of the longest substring that contains no repeated characters.",
        "examples": [{"input": 's = "abcabcbb"', "output": "3", "explanation": '"abc"'}, {"input": 's = "pwwkew"', "output": "3"}],
        "constraints": ["0 <= len(s) <= 5 * 10^4", "Aim for O(n) time"],
        "entry": {"python": "longest_unique", "javascript": "longestUnique"},
        "starter": _starter("longest_unique", "s", "longestUnique", "public int longestUnique(String s)", "int longestUnique(const std::string& s)"),
        "tests": [
            {"args": ["abcabcbb"], "expected": 3}, {"args": ["bbbbb"], "expected": 1}, {"args": ["pwwkew"], "expected": 3},
            {"args": [""], "expected": 0}, {"args": ["abba"], "expected": 2}, {"args": ["dvdf"], "expected": 3},
        ],
        "signals": [r"\b(?:left|start|window|last|seen|index)\b", r"\b(?:dict|map|Map|set|Set|HashMap)\b|\{\}"],
        "complexity": "O(n) time with a sliding window and the last index of each character.",
        "reference": "def longest_unique(s):\n    last = {}\n    start = best = 0\n    for i, ch in enumerate(s):\n        if ch in last and last[ch] >= start:\n            start = last[ch] + 1\n        last[ch] = i\n        best = max(best, i - start + 1)\n    return best\n",
    },
    {
        "id": "merge-intervals", "title": "Merge overlapping intervals", "difficulty": "medium", "topics": ("sorting", "intervals"),
        "statement": "Given a list of [start, end] intervals, merge all overlapping intervals (touching ends such as [1, 4] and [4, 5] overlap) and return them sorted by start.",
        "examples": [{"input": "intervals = [[1, 3], [2, 6], [8, 10], [15, 18]]", "output": "[[1, 6], [8, 10], [15, 18]]"}],
        "constraints": ["1 <= len(intervals) <= 10^4"],
        "entry": {"python": "merge_intervals", "javascript": "mergeIntervals"},
        "starter": _starter("merge_intervals", "intervals", "mergeIntervals", "public int[][] mergeIntervals(int[][] intervals)", "std::vector<std::vector<int>> mergeIntervals(std::vector<std::vector<int>>& intervals)"),
        "tests": [
            {"args": [[[1, 3], [2, 6], [8, 10], [15, 18]]], "expected": [[1, 6], [8, 10], [15, 18]]},
            {"args": [[[1, 4], [4, 5]]], "expected": [[1, 5]]},
            {"args": [[[5, 7], [1, 2]]], "expected": [[1, 2], [5, 7]]},
            {"args": [[[1, 10], [2, 3], [4, 5]]], "expected": [[1, 10]]},
        ],
        "signals": [r"\bsort", r"\bmax\b|Math\.max|std::max"],
        "complexity": "O(n log n) for the sort, then one linear pass.",
        "reference": "def merge_intervals(intervals):\n    result = []\n    for start, end in sorted(intervals):\n        if result and start <= result[-1][1]:\n            result[-1][1] = max(result[-1][1], end)\n        else:\n            result.append([start, end])\n    return result\n",
    },
    {
        "id": "top-k-frequent", "title": "Top K frequent values", "difficulty": "medium", "topics": ("hashing", "heap", "sorting"),
        "statement": "Return the k most frequent values in nums, most frequent first. Break ties by the smaller value first.",
        "examples": [{"input": "nums = [1, 1, 1, 2, 2, 3], k = 2", "output": "[1, 2]"}],
        "constraints": ["1 <= k <= number of distinct values"],
        "entry": {"python": "top_k_frequent", "javascript": "topKFrequent"},
        "starter": _starter("top_k_frequent", "nums, k", "topKFrequent", "public List<Integer> topKFrequent(int[] nums, int k)", "std::vector<int> topKFrequent(std::vector<int>& nums, int k)"),
        "tests": [
            {"args": [[1, 1, 1, 2, 2, 3], 2], "expected": [1, 2]}, {"args": [[4, 4, 5, 5, 6], 2], "expected": [4, 5]},
            {"args": [[9], 1], "expected": [9]}, {"args": [[3, 1, 3, 2, 2, 1, 1], 3], "expected": [1, 2, 3]},
        ],
        "signals": [r"\b(?:Counter|count|dict|map|Map|HashMap|freq)", r"\b(?:sort|sorted|heap|heapq|PriorityQueue|nlargest)\b"],
        "complexity": "O(n log n) by sorting counts, or O(n log k) with a heap of size k.",
        "reference": "from collections import Counter\n\ndef top_k_frequent(nums, k):\n    counts = Counter(nums)\n    return sorted(counts, key=lambda value: (-counts[value], value))[:k]\n",
    },
    {
        "id": "product-except-self", "title": "Product of all other elements", "difficulty": "medium", "topics": ("arrays", "prefix sums"),
        "statement": "Return a list where answer[i] is the product of every element of nums except nums[i]. Do not use division.",
        "examples": [{"input": "nums = [1, 2, 3, 4]", "output": "[24, 12, 8, 6]"}],
        "constraints": ["2 <= len(nums) <= 10^5", "O(n) time, no division"],
        "entry": {"python": "product_except_self", "javascript": "productExceptSelf"},
        "starter": _starter("product_except_self", "nums", "productExceptSelf", "public int[] productExceptSelf(int[] nums)", "std::vector<int> productExceptSelf(std::vector<int>& nums)"),
        "tests": [
            {"args": [[1, 2, 3, 4]], "expected": [24, 12, 8, 6]}, {"args": [[2, 0, 3]], "expected": [0, 6, 0]},
            {"args": [[-1, 1, 0, -3, 3]], "expected": [0, 0, 9, 0, 0]}, {"args": [[5, 2]], "expected": [2, 5]},
        ],
        "signals": [r"\b(?:prefix|suffix|left|right)\b"],
        "complexity": "O(n) time: multiply prefix products by suffix products.",
        "reference": "def product_except_self(nums):\n    n = len(nums)\n    out = [1] * n\n    prefix = 1\n    for i in range(n):\n        out[i] = prefix\n        prefix *= nums[i]\n    suffix = 1\n    for i in range(n - 1, -1, -1):\n        out[i] *= suffix\n        suffix *= nums[i]\n    return out\n",
    },
    {
        "id": "count-islands", "title": "Count islands in a grid", "difficulty": "medium", "topics": ("graphs", "BFS/DFS"),
        "statement": "Given a grid of '1' (land) and '0' (water), count the islands. An island is land connected horizontally or vertically.",
        "examples": [{"input": 'grid = [["1","1","0"],["0","1","0"],["0","0","1"]]', "output": "2"}],
        "constraints": ["1 <= rows, cols <= 300"],
        "entry": {"python": "count_islands", "javascript": "countIslands"},
        "starter": _starter("count_islands", "grid", "countIslands", "public int countIslands(char[][] grid)", "int countIslands(std::vector<std::vector<char>>& grid)"),
        "tests": [
            {"args": [[["1", "1", "0"], ["0", "1", "0"], ["0", "0", "1"]]], "expected": 2},
            {"args": [[["0", "0"], ["0", "0"]]], "expected": 0},
            {"args": [[["1", "0", "1", "0", "1"]]], "expected": 3},
            {"args": [[["1", "1"], ["1", "1"]]], "expected": 1},
        ],
        "signals": [r"\b(?:dfs|bfs|queue|stack|visit|seen|deque|recurs)", r"\[\s*-?1\s*,\s*0\s*\]|\(\s*-?1\s*,\s*0\s*\)|r\s*[+-]\s*1|i\s*[+-]\s*1"],
        "complexity": "O(rows × cols): each cell is visited once by DFS or BFS.",
        "reference": "def count_islands(grid):\n    rows, cols = len(grid), len(grid[0])\n    seen = set()\n    count = 0\n    for r in range(rows):\n        for c in range(cols):\n            if grid[r][c] == '1' and (r, c) not in seen:\n                count += 1\n                stack = [(r, c)]\n                seen.add((r, c))\n                while stack:\n                    i, j = stack.pop()\n                    for di, dj in ((1, 0), (-1, 0), (0, 1), (0, -1)):\n                        ni, nj = i + di, j + dj\n                        if 0 <= ni < rows and 0 <= nj < cols and grid[ni][nj] == '1' and (ni, nj) not in seen:\n                            seen.add((ni, nj))\n                            stack.append((ni, nj))\n    return count\n",
    },
    {
        "id": "group-anagrams", "title": "Group anagrams", "difficulty": "medium", "topics": ("hashing", "strings"),
        "statement": "Group words that are anagrams of each other. Return the groups with the words in each group sorted alphabetically, and the groups sorted by their first word.",
        "examples": [{"input": 'words = ["eat", "tea", "tan", "ate", "nat", "bat"]', "output": '[["ate", "eat", "tea"], ["bat"], ["nat", "tan"]]'}],
        "constraints": ["1 <= len(words) <= 10^4"],
        "entry": {"python": "group_anagrams", "javascript": "groupAnagrams"},
        "starter": _starter("group_anagrams", "words", "groupAnagrams", "public List<List<String>> groupAnagrams(String[] words)", "std::vector<std::vector<std::string>> groupAnagrams(std::vector<std::string>& words)"),
        "tests": [
            {"args": [["eat", "tea", "tan", "ate", "nat", "bat"]], "expected": [["ate", "eat", "tea"], ["bat"], ["nat", "tan"]]},
            {"args": [["a"]], "expected": [["a"]]},
            {"args": [["ab", "ba", "abc", "cab", "x"]], "expected": [["ab", "ba"], ["abc", "cab"], ["x"]]},
        ],
        "signals": [r"\b(?:sorted|sort|split\(''\)|join|defaultdict|dict|map|Map|HashMap)\b"],
        "complexity": "O(n · k log k): sort each word (length k) to build its key.",
        "reference": "from collections import defaultdict\n\ndef group_anagrams(words):\n    groups = defaultdict(list)\n    for word in words:\n        groups[''.join(sorted(word))].append(word)\n    return sorted(sorted(group) for group in groups.values())\n",
    },
    {
        "id": "meeting-rooms", "title": "Minimum meeting rooms", "difficulty": "hard", "topics": ("intervals", "heap", "sorting"),
        "statement": "Given meeting time intervals [start, end) where a meeting ending at t frees its room for another starting at t, return the minimum number of rooms needed.",
        "examples": [{"input": "meetings = [[0, 30], [5, 10], [15, 20]]", "output": "2"}, {"input": "meetings = [[1, 5], [5, 9]]", "output": "1"}],
        "constraints": ["0 <= len(meetings) <= 10^4"],
        "entry": {"python": "min_rooms", "javascript": "minRooms"},
        "starter": _starter("min_rooms", "meetings", "minRooms", "public int minRooms(int[][] meetings)", "int minRooms(std::vector<std::vector<int>>& meetings)"),
        "tests": [
            {"args": [[[0, 30], [5, 10], [15, 20]]], "expected": 2}, {"args": [[[1, 5], [5, 9]]], "expected": 1},
            {"args": [[]], "expected": 0}, {"args": [[[1, 4], [2, 5], [3, 6], [4, 7]]], "expected": 3},
        ],
        "signals": [r"\bsort", r"\b(?:heap|heapq|PriorityQueue|priority_queue|starts|ends|pointer)\b"],
        "complexity": "O(n log n): sort start and end times and sweep, or keep a min-heap of end times.",
        "reference": "import heapq\n\ndef min_rooms(meetings):\n    ends = []\n    for start, end in sorted(meetings):\n        if ends and ends[0] <= start:\n            heapq.heapreplace(ends, end)\n        else:\n            heapq.heappush(ends, end)\n    return len(ends)\n",
    },
    {
        "id": "lru-cache", "title": "LRU cache operations", "difficulty": "hard", "topics": ("design", "hashing", "linked list"),
        "statement": "Simulate a least-recently-used cache of the given capacity. ops is a list of [\"put\", key, value] or [\"get\", key]. A get returns the value (or -1 if absent) and marks the key as recently used; a put inserts or updates and evicts the least recently used key when over capacity. Return the results of the get operations in order.",
        "examples": [{"input": 'capacity = 2, ops = [["put",1,1],["put",2,2],["get",1],["put",3,3],["get",2],["get",3]]', "output": "[1, -1, 3]"}],
        "constraints": ["1 <= capacity <= 3000", "O(1) average time per operation"],
        "entry": {"python": "lru_results", "javascript": "lruResults"},
        "starter": _starter("lru_results", "capacity, ops", "lruResults", "public List<Integer> lruResults(int capacity, List<List<Object>> ops)", "std::vector<int> lruResults(int capacity, const std::vector<std::vector<int>>& ops)"),
        "tests": [
            {"args": [2, [["put", 1, 1], ["put", 2, 2], ["get", 1], ["put", 3, 3], ["get", 2], ["get", 3]]], "expected": [1, -1, 3]},
            {"args": [1, [["put", 1, 1], ["put", 1, 5], ["get", 1], ["put", 2, 2], ["get", 1]]], "expected": [5, -1]},
            {"args": [2, [["get", 9]]], "expected": [-1]},
            {"args": [2, [["put", 1, 1], ["put", 2, 2], ["put", 1, 10], ["put", 3, 3], ["get", 2], ["get", 1]]], "expected": [-1, 10]},
        ],
        "signals": [r"\b(?:OrderedDict|move_to_end|LinkedHashMap|Map|delete|popitem|list<|splice|doubly)\b"],
        "complexity": "O(1) per operation with a hash map plus a doubly linked list (OrderedDict / Map insertion order).",
        "reference": "from collections import OrderedDict\n\ndef lru_results(capacity, ops):\n    cache = OrderedDict()\n    out = []\n    for op in ops:\n        if op[0] == 'get':\n            key = op[1]\n            if key in cache:\n                cache.move_to_end(key)\n                out.append(cache[key])\n            else:\n                out.append(-1)\n        else:\n            key, value = op[1], op[2]\n            cache[key] = value\n            cache.move_to_end(key)\n            if len(cache) > capacity:\n                cache.popitem(last=False)\n    return out\n",
    },
    {
        "id": "word-break", "title": "Word break", "difficulty": "hard", "topics": ("dynamic programming", "strings"),
        "statement": "Return true if s can be split into a sequence of one or more words from the list words (words may be reused).",
        "examples": [{"input": 's = "applepenapple", words = ["apple", "pen"]', "output": "true"}, {"input": 's = "catsandog", words = ["cats", "dog", "sand", "and", "cat"]', "output": "false"}],
        "constraints": ["1 <= len(s) <= 300"],
        "entry": {"python": "word_break", "javascript": "wordBreak"},
        "starter": _starter("word_break", "s, words", "wordBreak", "public boolean wordBreak(String s, List<String> words)", "bool wordBreak(const std::string& s, std::vector<std::string>& words)"),
        "tests": [
            {"args": ["applepenapple", ["apple", "pen"]], "expected": True},
            {"args": ["catsandog", ["cats", "dog", "sand", "and", "cat"]], "expected": False},
            {"args": ["aaaaaaa", ["aaaa", "aaa"]], "expected": True},
            {"args": ["leetcode", ["leet", "code"]], "expected": True},
            {"args": ["ab", ["a"]], "expected": False},
        ],
        "signals": [r"\b(?:dp|memo|cache|lru_cache|range\(|for)\b"],
        "complexity": "O(n^2) checks with dp[i] = 'prefix of length i can be split'.",
        "reference": "def word_break(s, words):\n    vocab = set(words)\n    ok = [True] + [False] * len(s)\n    for i in range(1, len(s) + 1):\n        ok[i] = any(ok[j] and s[j:i] in vocab for j in range(i))\n    return ok[-1]\n",
    },
    # ----------------------------------------------------------------- SQL
    {
        "id": "sql-second-highest", "title": "Second-highest salary", "difficulty": "easy", "topics": ("SQL", "subqueries"), "language": "sql",
        "statement": "Table employees(id, name, dept, salary). Write a query that returns one row with one column, second_highest: the second-highest distinct salary, or NULL if it does not exist.",
        "setup": "CREATE TABLE employees (id INTEGER, name TEXT, dept TEXT, salary INTEGER);\nINSERT INTO employees VALUES (1,'Asha','Data',90000),(2,'Ravi','Data',70000),(3,'Meena','Web',90000),(4,'John','Web',60000);",
        "expected_rows": [[70000]], "ordered": True,
        "starter": {"sql": "-- employees(id, name, dept, salary)\nSELECT\n"},
        "signals": [r"(?i)\bMAX\b|\bDENSE_RANK\b|\bOFFSET\b|\bDISTINCT\b", r"(?i)\bSELECT\b"],
        "complexity": "A subquery with MAX, or DENSE_RANK() over salary descending.",
        "reference": "SELECT MAX(salary) AS second_highest FROM employees WHERE salary < (SELECT MAX(salary) FROM employees);",
    },
    {
        "id": "sql-earning-above-manager", "title": "Employees earning more than their manager", "difficulty": "medium", "topics": ("SQL", "self join"), "language": "sql",
        "statement": "Table staff(id, name, salary, manager_id). Return the names of employees who earn more than their manager, sorted by name.",
        "setup": "CREATE TABLE staff (id INTEGER, name TEXT, salary INTEGER, manager_id INTEGER);\nINSERT INTO staff VALUES (1,'Kiran',80000,NULL),(2,'Asha',95000,1),(3,'Ravi',60000,1),(4,'Zoya',70000,3),(5,'Dev',50000,2);",
        "expected_rows": [["Asha"], ["Zoya"]], "ordered": True,
        "starter": {"sql": "-- staff(id, name, salary, manager_id)\nSELECT\n"},
        "signals": [r"(?i)\bJOIN\b", r"(?i)\bORDER\s+BY\b"],
        "complexity": "Self join staff e to staff m on e.manager_id = m.id and compare salaries.",
        "reference": "SELECT e.name FROM staff e JOIN staff m ON e.manager_id = m.id WHERE e.salary > m.salary ORDER BY e.name;",
    },
    {
        "id": "sql-top-per-department", "title": "Top earner in each department", "difficulty": "hard", "topics": ("SQL", "window functions"), "language": "sql",
        "statement": "Table employees(id, name, dept, salary). Return dept, name and salary of the highest-paid employee in each department. If several tie, return all of them. Sort by dept, then name.",
        "setup": "CREATE TABLE employees (id INTEGER, name TEXT, dept TEXT, salary INTEGER);\nINSERT INTO employees VALUES (1,'Asha','Data',90000),(2,'Ravi','Data',90000),(3,'Meena','Web',85000),(4,'John','Web',60000),(5,'Sara','HR',50000);",
        "expected_rows": [["Data", "Asha", 90000], ["Data", "Ravi", 90000], ["HR", "Sara", 50000], ["Web", "Meena", 85000]], "ordered": True,
        "starter": {"sql": "-- employees(id, name, dept, salary)\nSELECT\n"},
        "signals": [r"(?i)\b(?:RANK|DENSE_RANK|PARTITION\s+BY|MAX\s*\()", r"(?i)\bORDER\s+BY\b"],
        "complexity": "RANK() OVER (PARTITION BY dept ORDER BY salary DESC) and keep rank 1, or join to per-department MAX.",
        "reference": "SELECT dept, name, salary FROM (SELECT dept, name, salary, RANK() OVER (PARTITION BY dept ORDER BY salary DESC) AS r FROM employees) WHERE r = 1 ORDER BY dept, name;",
    },
]


def _rank(seed: str, problem_id: str) -> str:
    return hashlib.sha256(f"{seed}|{problem_id}".encode()).hexdigest()


def pick_problems(level: str, count: int, *, sql_count: int = 0, seed: str = "", seen_ids: set[str] | None = None) -> list[dict[str, Any]]:
    """Problems for one interview: difficulty by level, unseen first, SQL tasks for data roles."""
    seen_ids = seen_ids or set()
    plan = list(LEVEL_DIFFICULTIES.get(level, LEVEL_DIFFICULTIES["mid"]))
    code_pool = [problem for problem in PROBLEMS if problem.get("language") != "sql"]
    sql_pool = [problem for problem in PROBLEMS if problem.get("language") == "sql"]
    chosen: list[dict[str, Any]] = []
    for index in range(min(sql_count, count, len(sql_pool))):
        wanted = plan[index % len(plan)]
        candidates = [item for item in sql_pool if item not in chosen]
        candidates.sort(key=lambda item: (item["id"] in seen_ids, item["difficulty"] != wanted, _rank(seed, item["id"])))
        chosen.append(candidates[0])
    for index in range(len(chosen), count):
        wanted = plan[index % len(plan)]
        candidates = [item for item in code_pool if item not in chosen]
        candidates.sort(key=lambda item: (item["id"] in seen_ids, item["difficulty"] != wanted, _rank(seed, item["id"])))
        if candidates:
            chosen.append(candidates[0])
    return chosen


def problem_payload(problem: dict[str, Any], language: str) -> dict[str, Any]:
    """What the interview page needs to show and run one problem (no reference solution)."""
    is_sql = problem.get("language") == "sql"
    language = "sql" if is_sql else language
    starter = problem["starter"].get(language) or problem["starter"].get("python", "")
    payload = {
        "problem_id": problem["id"], "title": problem["title"], "difficulty": problem["difficulty"],
        "topics": list(problem.get("topics") or ()), "statement": problem["statement"],
        "examples": problem.get("examples") or [], "constraints": problem.get("constraints") or [],
        "language": language, "starter_code": starter, "runnable": language in RUNNABLE_LANGUAGES,
        "complexity_hint": "State the time and space complexity of your solution in a comment.",
    }
    if is_sql:
        payload.update(setup=problem["setup"], expected_rows=problem["expected_rows"], ordered=bool(problem.get("ordered", True)))
    else:
        payload.update(entry=problem["entry"].get(language, problem["entry"]["python"]), tests=problem["tests"])
    return payload


def problem_by_id(problem_id: str) -> dict[str, Any] | None:
    return next((problem for problem in PROBLEMS if problem["id"] == problem_id), None)


def question_text(problem: dict[str, Any], language_label: str) -> str:
    language_label = "SQL" if problem.get("language") == "sql" else language_label
    return f"Coding ({problem['difficulty']}): {problem['title']}. {problem['statement']} Write your solution in {language_label}."
