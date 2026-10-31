"""Code-reading MCQs for technical mock tests.

Real screening rounds (campus drives, HackerRank/HackerEarth screens, lateral
online tests) ask candidates to trace code, predict output, spot bugs and
estimate complexity. Each item here carries the snippet separately from the
prompt so the page can show it as code.

Correctness is enforced by tests: every item with ``verify="stdout"`` is run
with the real interpreter or compiler (Python, Node.js, Java, C++, SQLite) and
its correct option must equal the program's output exactly. Difficulty:

- easy: one construct, direct trace (an operator, a slice, a basic loop)
- medium: a language rule people commonly get wrong (mutability, scope,
  integer division, NULL handling, references)
- hard: several interacting rules or multi-step state (closures over loop
  variables, aliasing, recursion, window functions, overflow)
"""

from __future__ import annotations

from typing import Any

CodeQuestion = dict[str, Any]


def q(difficulty: str, prompt: str, code: str, options: tuple[str, str, str, str], answer: int, explanation: str,
      *, verify: str = "stdout", setup: str = "") -> CodeQuestion:
    return {
        "difficulty": difficulty, "prompt": prompt, "code": code.strip("\n"), "options": options, "answer": answer,
        "explanation": explanation, "verify": verify, "setup": setup.strip("\n"),
    }


CODE_TOPICS: dict[str, dict[str, Any]] = {
    "python": {
        "language": "python",
        "questions": [
            q("easy", "What does this Python code print?", """
nums = [3, 1, 4, 1, 5]
print(nums[1:4])
""", ("[1, 4, 1]", "[3, 1, 4]", "[1, 4, 1, 5]", "[4, 1, 5]"), 0, "Slicing [1:4] takes indexes 1, 2 and 3; the end index is excluded."),
            q("easy", "What does this Python code print?", """
word = "placement"
print(word[::-1][:3])
""", ("tne", "pla", "ent", "tnem"), 0, "[::-1] reverses the string to 'tnemecalp'; the first three characters are 'tne'."),
            q("easy", "What does this Python code print?", """
total = 0
for i in range(1, 6, 2):
    total += i
print(total)
""", ("9", "15", "6", "12"), 0, "range(1, 6, 2) yields 1, 3, 5, which sum to 9."),
            q("easy", "What does this Python code print?", """
scores = {"asha": 82, "ravi": 74}
scores["meena"] = 91
print(len(scores), scores.get("john", 0))
""", ("3 0", "2 0", "3 None", "It raises a KeyError"), 0, "Adding a key makes 3 entries; get() returns the default 0 for a missing key instead of raising."),
            q("medium", "What does this Python code print?", """
a = [1, 2, 3]
b = a
b.append(4)
print(a, a is b)
""", ("[1, 2, 3, 4] True", "[1, 2, 3] False", "[1, 2, 3, 4] False", "[1, 2, 3] True"), 0, "b = a binds a second name to the same list, so the append is visible through a."),
            q("medium", "What does this Python code print?", """
def add(item, bucket=[]):
    bucket.append(item)
    return bucket

add("x")
print(add("y"))
""", ("['x', 'y']", "['y']", "['x']", "[]"), 0, "The default list is created once when the function is defined and reused across calls."),
            q("medium", "What does this Python code print?", """
data = [("b", 2), ("a", 2), ("c", 1)]
print(sorted(data, key=lambda pair: (-pair[1], pair[0])))
""", ("[('a', 2), ('b', 2), ('c', 1)]", "[('b', 2), ('a', 2), ('c', 1)]", "[('c', 1), ('a', 2), ('b', 2)]", "[('a', 2), ('c', 1), ('b', 2)]"), 0, "The key sorts by count descending, then by name ascending to break the tie."),
            q("medium", "What does this Python code print?", """
from collections import Counter
print(Counter("banana").most_common(2))
""", ("[('a', 3), ('n', 2)]", "[('b', 1), ('a', 3)]", "[('a', 3), ('b', 1)]", "[('n', 2), ('a', 3)]"), 0, "'a' appears 3 times and 'n' twice; most_common orders by count."),
            q("medium", "What does this Python code print?", """
x = 10
def change():
    x = 20
    return x
change()
print(x)
""", ("10", "20", "None", "It raises an UnboundLocalError"), 0, "Assignment inside the function creates a new local x; the global x is unchanged."),
            q("medium", "What does this Python code print?", """
matrix = [[0] * 2] * 2
matrix[0][0] = 5
print(matrix)
""", ("[[5, 0], [5, 0]]", "[[5, 0], [0, 0]]", "[[5, 5], [0, 0]]", "[[0, 0], [0, 0]]"), 0, "Multiplying the outer list repeats a reference to the same inner list, so both rows change."),
            q("hard", "What does this Python code print?", """
funcs = [lambda: i for i in range(3)]
print([f() for f in funcs])
""", ("[2, 2, 2]", "[0, 1, 2]", "[0, 0, 0]", "[3, 3, 3]"), 0, "Each lambda looks up i when called, after the loop has finished with i = 2 (late binding)."),
            q("hard", "What does this Python code print?", """
def gen():
    for n in range(3):
        yield n * n

g = gen()
print(sum(g), sum(g))
""", ("5 0", "5 5", "0 5", "14 14"), 0, "A generator is exhausted after one pass: 0 + 1 + 4 = 5, then the second sum sees nothing."),
            q("hard", "What does this Python code print?", """
import copy
a = [[1, 2], [3]]
b = copy.copy(a)
c = copy.deepcopy(a)
a[0].append(9)
print(len(b[0]), len(c[0]))
""", ("3 2", "2 2", "3 3", "2 3"), 0, "A shallow copy shares the inner lists, so b sees the append; the deep copy does not."),
            q("hard", "What does this Python code print?", """
def f(n, memo={}):
    if n in memo:
        return memo[n]
    if n < 2:
        return n
    memo[n] = f(n - 1) + f(n - 2)
    return memo[n]

print(f(10), len(f.__defaults__[0]))
""", ("55 9", "55 10", "89 9", "55 0"), 0, "f(10) = 55 and the shared default dict memoises results for n = 2 to 10, which is 9 keys."),
        ],
    },
    "sql": {
        "language": "sql",
        "setup": """
CREATE TABLE emp (id INTEGER, name TEXT, dept TEXT, salary INTEGER, manager_id INTEGER);
INSERT INTO emp VALUES (1, 'Asha', 'Data', 90000, NULL), (2, 'Ravi', 'Data', 70000, 1), (3, 'Meena', 'Web', 70000, 1),
 (4, 'John', 'Web', 60000, 3), (5, 'Sara', 'Data', NULL, 1);
""",
        "questions": [
            q("easy", "Using the emp table below, what does this query return?", """
SELECT COUNT(*), COUNT(salary) FROM emp;
""", ("5|4", "5|5", "4|4", "4|5"), 0, "COUNT(*) counts all 5 rows; COUNT(salary) skips Sara's NULL salary."),
            q("easy", "Using the emp table below, what does this query return?", """
SELECT dept, COUNT(*) FROM emp GROUP BY dept ORDER BY dept;
""", ("Data|3\nWeb|2", "Data|2\nWeb|2", "Data|3\nWeb|3", "Web|2\nData|3"), 0, "Data has Asha, Ravi and Sara; Web has Meena and John; ORDER BY dept puts Data first."),
            q("medium", "Using the emp table below, what does this query return?", """
SELECT dept, AVG(salary) FROM emp GROUP BY dept HAVING COUNT(*) > 2;
""", ("Data|80000.0", "Data|53333.333333333336", "Web|65000.0", "Data|80000.0\nWeb|65000.0"), 0, "Only Data has more than 2 rows; AVG ignores the NULL salary, so (90000 + 70000) / 2 = 80000."),
            q("medium", "Using the emp table below, what does this query return?", """
SELECT name FROM emp WHERE salary <> 70000 ORDER BY name;
""", ("Asha\nJohn", "Asha\nJohn\nSara", "Asha\nSara", "John"), 0, "A comparison with NULL is unknown, not true, so Sara is excluded as well as the two 70000 rows."),
            q("medium", "Using the emp table below, what does this query return?", """
SELECT e.name, m.name FROM emp e LEFT JOIN emp m ON e.manager_id = m.id WHERE e.dept = 'Web' ORDER BY e.id;
""", ("Meena|Asha\nJohn|Meena", "Meena|\nJohn|Meena", "Meena|Asha", "John|Meena"), 0, "A self join maps each employee to the manager row: Meena reports to Asha and John to Meena."),
            q("medium", "Using the emp table below, what does this query return?", """
SELECT MAX(salary) FROM emp WHERE salary < (SELECT MAX(salary) FROM emp);
""", ("70000", "90000", "60000", "NULL"), 0, "The subquery finds 90000; the highest salary below it is 70000 (the second-highest distinct value)."),
            q("hard", "Using the emp table below, what does this query return?", """
SELECT name, RANK() OVER (ORDER BY salary DESC) AS r
FROM emp WHERE salary IS NOT NULL ORDER BY r, name;
""", ("Asha|1\nMeena|2\nRavi|2\nJohn|4", "Asha|1\nMeena|2\nRavi|2\nJohn|3", "Asha|1\nRavi|2\nMeena|3\nJohn|4", "Asha|1\nMeena|1\nRavi|2\nJohn|3"), 0, "RANK gives tied rows the same rank and skips the next value, so John is 4th; DENSE_RANK would give 3."),
            q("hard", "Using the emp table below, what does this query return?", """
SELECT dept, name FROM (
  SELECT dept, name, ROW_NUMBER() OVER (PARTITION BY dept ORDER BY salary DESC) AS rn FROM emp
) WHERE rn = 1 ORDER BY dept;
""", ("Data|Asha\nWeb|Meena", "Data|Sara\nWeb|Meena", "Data|Asha\nWeb|John", "Data|Asha"), 0, "ROW_NUMBER restarts per department; the top earner is Asha in Data and Meena in Web (SQLite sorts NULL last in DESC)."),
            q("hard", "Using the emp table below, what does this query return?", """
SELECT COUNT(DISTINCT salary), SUM(CASE WHEN salary >= 70000 THEN 1 ELSE 0 END) FROM emp;
""", ("3|3", "4|3", "3|4", "4|4"), 0, "Distinct non-NULL salaries are 90000, 70000 and 60000; three rows have salary >= 70000 (NULL fails the test)."),
        ],
    },
    "javascript": {
        "language": "javascript",
        "questions": [
            q("easy", "What does this JavaScript code log?", """
const arr = [10, 20, 30];
console.log(arr.map(x => x / 10).join("-"));
""", ("1-2-3", "10-20-30", "1,2,3", "[1, 2, 3]"), 0, "map divides each value by 10 and join builds '1-2-3'."),
            q("easy", "What does this JavaScript code log?", """
console.log(typeof null, typeof undefined);
""", ("object undefined", "null undefined", "object object", "undefined undefined"), 0, "typeof null is 'object' (a historical quirk); typeof undefined is 'undefined'."),
            q("easy", "What does this JavaScript code log?", """
console.log("5" + 3, "5" - 3);
""", ("53 2", "8 2", "53 53", "8 8"), 0, "+ with a string concatenates; - converts both operands to numbers."),
            q("medium", "What does this JavaScript code log?", """
console.log([1, 2, 3] == "1,2,3", [] === []);
""", ("true false", "false false", "true true", "false true"), 0, "Loose equality converts the array to the string '1,2,3'; two different array objects are never strictly equal."),
            q("medium", "What does this JavaScript code log?", """
const nums = [10, 1, 5];
nums.sort();
console.log(nums);
""", ("[ 1, 10, 5 ]", "[ 1, 5, 10 ]", "[ 10, 5, 1 ]", "[ 10, 1, 5 ]"), 0, "Default sort compares values as strings, so '10' comes before '5'. Pass (a, b) => a - b for numeric order."),
            q("medium", "What does this JavaScript code log?", """
const user = { name: "Asha", skills: ["SQL"] };
const copy = { ...user };
copy.skills.push("Python");
console.log(user.skills.length);
""", ("2", "1", "0", "undefined"), 0, "Spread makes a shallow copy; both objects share the same skills array."),
            q("medium", "What does this JavaScript code log?", """
console.log([3, 1, 2].reduce((acc, x) => acc + x * 2, 1));
""", ("13", "12", "7", "6"), 0, "Starting at 1: 1 + 6 + 2 + 4 = 13."),
            q("hard", "In what order does Node.js log these lines?", """
console.log("A");
setTimeout(() => console.log("B"), 0);
Promise.resolve().then(() => console.log("C"));
console.log("D");
""", ("A\nD\nC\nB", "A\nB\nC\nD", "A\nC\nD\nB", "A\nD\nB\nC"), 0, "Synchronous code runs first, then microtasks (the promise), then the timer callback."),
            q("hard", "What does this JavaScript code log?", """
for (var i = 0; i < 3; i++) {
  setTimeout(() => process.stdout.write(String(i)), 0);
}
setTimeout(() => console.log(""), 1);
""", ("333", "012", "000", "222"), 0, "var is function-scoped, so every callback sees the final i = 3. With let each iteration gets its own binding (012)."),
            q("hard", "What does this JavaScript code log?", """
function counter() {
  let count = 0;
  return { inc: () => ++count, get: () => count };
}
const a = counter(), b = counter();
a.inc(); a.inc(); b.inc();
console.log(a.get(), b.get());
""", ("2 1", "3 3", "1 1", "2 2"), 0, "Each call to counter() creates its own closure with a separate count."),
        ],
    },
    "java": {
        "language": "java",
        "questions": [
            q("easy", "What does this Java program print?", """
public class Main {
    public static void main(String[] args) {
        int a = 7, b = 2;
        System.out.println(a / b + " " + a % b + " " + (double) a / b);
    }
}
""", ("3 1 3.5", "3.5 1 3.5", "3 1 3.0", "4 1 3.5"), 0, "Integer division truncates to 3; the cast happens before dividing, giving 3.5."),
            q("easy", "What does this Java program print?", """
public class Main {
    public static void main(String[] args) {
        StringBuilder sb = new StringBuilder("java");
        sb.append("21").reverse();
        System.out.println(sb);
    }
}
""", ("12avaj", "java21", "avaj21", "21java"), 0, "append gives 'java21' and reverse flips it to '12avaj'."),
            q("medium", "What does this Java program print?", """
public class Main {
    public static void main(String[] args) {
        String a = "hello";
        String b = new String("hello");
        System.out.println((a == b) + " " + a.equals(b));
    }
}
""", ("false true", "true true", "false false", "true false"), 0, "== compares references (new String creates a new object); equals compares characters."),
            q("medium", "What does this Java program print?", """
import java.util.*;
public class Main {
    public static void main(String[] args) {
        List<Integer> list = new ArrayList<>(List.of(5, 6, 7));
        list.remove(1);
        list.remove(Integer.valueOf(5));
        System.out.println(list);
    }
}
""", ("[7]", "[6]", "[5, 7]", "[6, 7]"), 0, "remove(1) removes the element at index 1 (6); remove(Integer.valueOf(5)) removes the value 5."),
            q("medium", "What does this Java program print?", """
public class Main {
    static void change(int[] arr, int x) { arr[0] = 99; x = 99; }
    public static void main(String[] args) {
        int[] arr = {1, 2};
        int x = 1;
        change(arr, x);
        System.out.println(arr[0] + " " + x);
    }
}
""", ("99 1", "1 1", "99 99", "1 99"), 0, "Java passes the array reference by value, so the array contents change; the primitive copy does not."),
            q("hard", "What does this Java program print?", """
public class Main {
    public static void main(String[] args) {
        int big = Integer.MAX_VALUE;
        long safe = big + 1L;
        System.out.println((big + 1) + " " + safe);
    }
}
""", ("-2147483648 2147483648", "2147483648 2147483648", "-2147483648 -2147483648", "It throws an ArithmeticException"), 0, "int addition silently overflows to Integer.MIN_VALUE; adding a long literal promotes the sum to long first."),
            q("hard", "What does this Java program print?", """
public class Main {
    static int f() {
        try { return 1; }
        finally { System.out.print("F "); }
    }
    public static void main(String[] args) {
        System.out.println(f());
    }
}
""", ("F 1", "1 F", "1", "F"), 0, "The finally block runs before the method actually returns, so 'F ' is printed first."),
            q("hard", "What does this Java program print?", """
import java.util.*;
public class Main {
    public static void main(String[] args) {
        Map<String, Integer> m = new HashMap<>();
        for (String w : "to be or not to be".split(" ")) m.merge(w, 1, Integer::sum);
        System.out.println(m.get("to") + m.get("be") + " " + m.size());
    }
}
""", ("4 4", "22 4", "4 6", "22 6"), 0, "Integer addition happens before string concatenation: 2 + 2 = 4, and there are 4 distinct words."),
        ],
    },
    "cpp": {
        "language": "cpp",
        "questions": [
            q("easy", "What does this C++ program print?", """
#include <iostream>
int main() {
    int total = 0;
    for (int i = 1; i <= 4; i++) total += i * i;
    std::cout << total;
}
""", ("30", "16", "10", "20"), 0, "The loop adds 1 + 4 + 9 + 16 = 30."),
            q("easy", "What does this C++ program print?", """
#include <iostream>
#include <vector>
int main() {
    std::vector<int> v = {4, 8, 15};
    v.push_back(16);
    std::cout << v.size() << " " << v.back();
}
""", ("4 16", "3 15", "4 15", "16 4"), 0, "push_back adds 16 at the end, making 4 elements."),
            q("easy", "What does this C++ program print?", """
#include <iostream>
int main() {
    int a = 17, b = 5;
    std::cout << a / b << " " << a % b;
}
""", ("3 2", "3.4 2", "3 3", "4 2"), 0, "Integer division truncates (17 / 5 = 3) and % gives the remainder 2."),
            q("medium", "What does this C++ program print?", """
#include <iostream>
void byValue(int n) { n = 10; }
void byRef(int &n) { n = 20; }
int main() {
    int a = 1, b = 1;
    byValue(a);
    byRef(b);
    std::cout << a << " " << b;
}
""", ("1 20", "10 20", "1 1", "10 1"), 0, "Only the reference parameter changes the caller's variable."),
            q("medium", "What does this C++ program print?", """
#include <iostream>
int main() {
    int arr[] = {1, 2, 3, 4, 5};
    int *p = arr + 1;
    std::cout << *(p + 2) << " " << sizeof(arr) / sizeof(arr[0]);
}
""", ("4 5", "3 5", "4 4", "5 5"), 0, "p points at arr[1], so p + 2 is arr[3] = 4; sizeof gives the element count 5."),
            q("medium", "What does this C++ program print?", """
#include <iostream>
#include <string>
int main() {
    std::string s = "interview";
    std::cout << s.substr(2, 3) << " " << s.find('v');
}
""", ("ter 5", "nte 5", "ter 6", "erv 5"), 0, "substr(2, 3) takes 3 characters from index 2; 'v' is at index 5."),
            q("hard", "What does this C++ program print?", """
#include <iostream>
struct Base { virtual const char* who() { return "Base"; } };
struct Derived : Base { const char* who() override { return "Derived"; } };
int main() {
    Derived d;
    Base &ref = d;
    Base copy = d;
    std::cout << ref.who() << " " << copy.who();
}
""", ("Derived Base", "Derived Derived", "Base Base", "Base Derived"), 0, "Virtual dispatch works through the reference; copying into a Base object slices off the Derived part."),
            q("hard", "What does this C++ program print?", """
#include <iostream>
int fib(int n) { return n < 2 ? n : fib(n - 1) + fib(n - 2); }
int main() {
    int calls = 0;
    for (int i = 0; i < 5; i++) calls += fib(i);
    std::cout << calls;
}
""", ("7", "5", "12", "8"), 0, "fib(0..4) = 0, 1, 1, 2, 3, which sum to 7."),
        ],
    },
    "dsa": {
        "language": "python",
        "questions": [
            q("easy", "What is the time complexity of this function for a list of length n?", """
def has_pair(nums, target):
    seen = set()
    for x in nums:
        if target - x in seen:
            return True
        seen.add(x)
    return False
""", ("O(n)", "O(n^2)", "O(n log n)", "O(1)"), 0, "One pass with O(1) average set lookups gives O(n) time (and O(n) extra space).", verify="none"),
            q("easy", "What does this code print?", """
stack = []
for ch in "(()":
    if ch == "(":
        stack.append(ch)
    else:
        stack.pop()
print(len(stack) == 0, len(stack))
""", ("False 1", "True 0", "False 2", "True 1"), 0, "Two opens and one close leave one '(' on the stack, so the string is unbalanced."),
            q("medium", "What does this binary search print?", """
def search(a, t):
    lo, hi, steps = 0, len(a) - 1, 0
    while lo <= hi:
        steps += 1
        mid = (lo + hi) // 2
        if a[mid] == t:
            return mid, steps
        if a[mid] < t:
            lo = mid + 1
        else:
            hi = mid - 1
    return -1, steps

print(search([2, 5, 8, 12, 16, 23, 38, 56, 72, 91], 23))
""", ("(5, 3)", "(5, 2)", "(6, 2)", "(5, 1)"), 0, "mid is index 4 (16 < 23), then 7 (56 > 23), then 5 (23): found at index 5 in 3 steps."),
            q("medium", "What does this code print?", """
from collections import deque
graph = {"A": ["B", "C"], "B": ["D"], "C": ["D", "E"], "D": [], "E": []}
order, queue, seen = [], deque(["A"]), {"A"}
while queue:
    node = queue.popleft()
    order.append(node)
    for nxt in graph[node]:
        if nxt not in seen:
            seen.add(nxt)
            queue.append(nxt)
print("".join(order))
""", ("ABCDE", "ABDCE", "ACEBD", "ABCED"), 0, "Breadth-first search visits level by level: A, then B and C, then D and E."),
            q("medium", "What is the worst-case time complexity of inserting n items one by one into an unbalanced binary search tree?", """
# keys arrive already sorted: 1, 2, 3, ..., n
for key in range(1, n + 1):
    bst_insert(root, key)
""", ("O(n^2)", "O(n log n)", "O(n)", "O(log n)"), 0, "Sorted input makes the tree a linked list; insert i walks i nodes, so the total is about n^2 / 2.", verify="none"),
            q("medium", "What does this dynamic-programming code print?", """
def ways(n):
    dp = [0] * (n + 1)
    dp[0] = 1
    for i in range(1, n + 1):
        dp[i] = dp[i - 1] + (dp[i - 2] if i >= 2 else 0)
    return dp[n]

print(ways(5))
""", ("8", "5", "13", "10"), 0, "This counts ways to climb 5 stairs taking 1 or 2 steps: 1, 1, 2, 3, 5, 8."),
            q("hard", "What does this code print?", """
def merge(intervals):
    intervals.sort()
    out = [intervals[0]]
    for start, end in intervals[1:]:
        if start <= out[-1][1]:
            out[-1][1] = max(out[-1][1], end)
        else:
            out.append([start, end])
    return out

print(merge([[8, 10], [1, 3], [2, 6], [15, 18], [6, 7]]))
""", ("[[1, 7], [8, 10], [15, 18]]", "[[1, 6], [6, 7], [8, 10], [15, 18]]", "[[1, 3], [2, 7], [8, 10], [15, 18]]", "[[1, 10], [15, 18]]"), 0, "After sorting, [1,3], [2,6] and [6,7] overlap into [1,7]; the others stay separate."),
            q("hard", "What does this code print?", """
import heapq
nums = [7, 2, 9, 4, 1, 8]
heap = []
for x in nums:
    heapq.heappush(heap, x)
    if len(heap) > 3:
        heapq.heappop(heap)
print(sorted(heap), heap[0])
""", ("[7, 8, 9] 7", "[1, 2, 4] 1", "[7, 8, 9] 9", "[4, 7, 8] 4"), 0, "A size-3 min-heap keeps the three largest values; its root is the 3rd largest (7)."),
            q("hard", "What does this recursive function print?", """
def perms(s):
    if len(s) <= 1:
        return [s]
    return [s[i] + p for i in range(len(s)) for p in perms(s[:i] + s[i + 1:])]

result = perms("abc")
print(len(result), result[3])
""", ("6 bca", "6 bac", "3 cab", "6 cab"), 0, "There are 3! = 6 permutations in order abc, acb, bac, bca, cab, cba; index 3 is 'bca'."),
        ],
    },
    "data_analysis": {
        "language": "python",
        "questions": [
            q("medium", "What does this pandas code print?", """
import pandas as pd
df = pd.DataFrame({"team": ["a", "b", "a", "b"], "sales": [10, 20, 30, None]})
print(df.groupby("team")["sales"].mean().tolist())
""", ("[20.0, 20.0]", "[20.0, 10.0]", "[20.0, nan]", "[40.0, 20.0]"), 0, "mean() skips NaN by default: team a = (10 + 30) / 2, team b = 20.", verify="pandas"),
            q("medium", "What does this pandas code print?", """
import pandas as pd
df = pd.DataFrame({"x": [5, 6, 7]}, index=[10, 20, 30])
print(df.loc[20, "x"], df.iloc[2, 0])
""", ("6 7", "6 6", "7 7", "It raises a KeyError"), 0, "loc uses the index label 20; iloc uses position 2.", verify="pandas"),
            q("hard", "What does this pandas code print?", """
import pandas as pd
left = pd.DataFrame({"id": [1, 2, 3]})
right = pd.DataFrame({"id": [2, 3, 3], "v": [1, 2, 3]})
print(len(left.merge(right, on="id", how="left")))
""", ("4", "3", "5", "2"), 0, "id 1 keeps one unmatched row, id 2 matches once and id 3 matches twice: 1 + 1 + 2 = 4 rows.", verify="pandas"),
        ],
    },
}
