"""More aptitude, reasoning and verbal-ability questions.

These rounds appear in nearly every Indian campus and lateral screening test
(AMCAT, eLitmus, TCS NQT, company-run online tests), for technical and
non-technical roles alike. Same tuple format as ``mock_test_bank``:
``(difficulty, question, options, correct_index, explanation)``. Numeric answers
are checked by ``tests/test_question_quality.py``.
"""

from __future__ import annotations

from .mock_test_bank import Question

EXTRA_QUESTIONS: dict[str, list[Question]] = {
    "aptitude": [
        ("easy", "A shirt marked at ₹1,200 is sold at a 25% discount. What is the selling price?",
         ("₹900", "₹950", "₹875", "₹1,000"), 0, "25% of 1,200 is 300, so the price is 1,200 - 300 = ₹900."),
        ("easy", "What is the average of 12, 18, 24 and 30?", ("21", "20", "22", "24"), 0, "(12 + 18 + 24 + 30) / 4 = 84 / 4 = 21."),
        ("easy", "If 8 pens cost ₹96, what do 5 pens cost?", ("₹60", "₹56", "₹64", "₹48"), 0, "One pen costs 96 / 8 = ₹12, so 5 pens cost ₹60."),
        ("easy", "A number increased by 20% becomes 360. What is the number?", ("300", "288", "320", "340"), 0, "1.2 × n = 360, so n = 300."),
        ("medium", "Two pipes fill a tank in 12 hours and 15 hours. How long do they take together?",
         ("6 h 40 min", "6 h 30 min", "7 h 30 min", "13 h 30 min"), 0, "Together they fill 1/12 + 1/15 = 9/60 per hour, so 60/9 h = 6 h 40 min."),
        ("medium", "A car travels 120 km at 40 km/h and returns at 60 km/h. What is the average speed for the round trip?",
         ("48 km/h", "50 km/h", "52 km/h", "45 km/h"), 0, "Total distance 240 km over 3 h + 2 h = 5 h gives 48 km/h (not the simple average of 50)."),
        ("medium", "What is the compound interest on ₹10,000 at 10% per annum for 2 years, compounded yearly?",
         ("₹2,100", "₹2,000", "₹2,200", "₹1,900"), 0, "10,000 × 1.1² = 12,100, so the interest is ₹2,100."),
        ("medium", "The ages of A and B are in the ratio 4:5. After 5 years the ratio will be 5:6. What is A's present age?",
         ("20", "25", "16", "24"), 0, "(4x + 5)/(5x + 5) = 5/6 gives x = 5, so A is 20."),
        ("medium", "A shopkeeper marks goods 40% above cost and then gives a 20% discount. What is the profit percentage?",
         ("12%", "20%", "16%", "8%"), 0, "1.40 × 0.80 = 1.12 of cost, a 12% profit."),
        ("hard", "In how many different ways can the letters of the word LEVEL be arranged?", ("30", "60", "120", "20"), 0,
         "5! / (2! × 2!) = 120 / 4 = 30, because L and E each repeat twice."),
        ("hard", "A boat goes 24 km downstream in 2 hours and returns upstream in 3 hours. What is the speed of the stream?",
         ("2 km/h", "4 km/h", "10 km/h", "1 km/h"), 0, "Downstream 12 km/h, upstream 8 km/h; the stream is half the difference, 2 km/h."),
        ("hard", "Two fair dice are thrown. What is the probability that the sum is 8?", ("5/36", "1/6", "1/9", "7/36"), 0,
         "(2,6), (3,5), (4,4), (5,3), (6,2) are 5 of the 36 outcomes."),
        ("hard", "A sum of money doubles in 5 years at simple interest. In how many years will it become four times?",
         ("15", "10", "20", "12"), 0, "Doubling means 100% interest in 5 years (20% a year); four times needs 300%, which takes 15 years."),
    ],
    "reasoning": [
        ("easy", "Find the next letter: A, C, F, J, O, ?", ("U", "T", "V", "S"), 0, "The gaps grow by one each time (+2, +3, +4, +5), so the next is O + 6 = U."),
        ("easy", "Find the odd one out: 121, 144, 169, 190", ("190", "121", "144", "169"), 0, "121, 144 and 169 are perfect squares (11², 12², 13²); 190 is not."),
        ("easy", "If the 1st of a month is a Monday, what day is the 22nd?", ("Monday", "Sunday", "Tuesday", "Wednesday"), 0,
         "The 8th, 15th and 22nd fall exactly one, two and three weeks later, so the 22nd is a Monday."),
        ("medium", "In a certain code PAPER is written as QBQFS. How is PENCIL written in that code?",
         ("QFODJM", "QFODJL", "OFODJM", "QEODJM"), 0, "Each letter moves one place forward: P→Q, E→F, N→O, C→D, I→J, L→M."),
        ("medium", "Ravi walks 5 km north, turns right and walks 3 km, then turns right and walks 5 km. Where is he now relative to his start?",
         ("3 km East", "3 km West", "13 km East", "5 km South"), 0, "North 5, east 3, south 5: he ends 3 km east of the start."),
        ("medium", "Statements: All engineers are graduates. No graduate is unemployed. Which conclusion follows?",
         ("No engineer is unemployed", "Some engineers are unemployed", "All graduates are engineers", "Some unemployed people are engineers"), 0,
         "Every engineer is a graduate and no graduate is unemployed, so no engineer is unemployed."),
        ("medium", "Find the missing number: 4, 9, 19, 39, ?", ("79", "78", "59", "81"), 0, "Each term is double the previous plus one: 39 × 2 + 1 = 79."),
        ("hard", "In a row of 40 students, Asha is 14th from the left. What is her position from the right?",
         ("27th", "26th", "28th", "25th"), 0, "Position from right = 40 - 14 + 1 = 27."),
        ("hard", "If 1 January 2025 was a Wednesday, what day was 1 January 2026?", ("Thursday", "Friday", "Wednesday", "Tuesday"), 0,
         "2025 is not a leap year; 365 days is 52 weeks and 1 day, so the day moves forward by one."),
        ("hard", "A cube painted on all faces is cut into 27 equal smaller cubes. How many small cubes have exactly two painted faces?",
         ("12", "8", "6", "24"), 0, "Only the middle cube of each of the 12 edges has exactly two painted faces."),
        ("hard", "Pointing to a photo, Arjun says, \"Her mother is the only daughter of my mother.\" How is the woman in the photo related to Arjun?",
         ("Niece", "Daughter", "Sister", "Cousin"), 0, "The only daughter of Arjun's mother is his sister, so the woman is his sister's daughter: his niece."),
    ],
    "verbal": [
        ("easy", "Choose the correctly spelled word.", ("Accommodate", "Acommodate", "Accomodate", "Acomodate"), 0,
         "Accommodate has a double c and a double m."),
        ("easy", "Choose the word closest in meaning to 'concise'.", ("Brief", "Detailed", "Unclear", "Lengthy"), 0, "Concise means expressed in few words: brief."),
        ("easy", "Choose the opposite of 'expand'.", ("Contract", "Enlarge", "Extend", "Spread"), 0, "To contract is to become smaller, the opposite of expand."),
        ("easy", "Fill in the blank: She has been working here ___ 2021.", ("since", "for", "from", "by"), 0,
         "'Since' introduces a point in time with the present perfect; 'for' is used with a duration."),
        ("easy", "Which is the most professional way to open an email to a recruiter you have not met?",
         ("Dear Ms. Rao,", "Hey Rao!", "Hi dear,", "Yo team,"), 0, "A formal salutation with title and surname is appropriate for a first message."),
        ("medium", "Identify the error: \"Each of the candidates have submitted their resume.\"",
         ("'have' should be 'has'", "'Each' should be 'All'", "'submitted' should be 'submit'", "There is no error"), 0,
         "'Each' is singular, so the verb should be 'has'."),
        ("medium", "Choose the grammatically correct sentence.",
         ("Neither the manager nor the team members were informed.", "Neither the manager nor the team members was informed.",
          "Neither the manager or the team members were informed.", "Neither the manager nor the team members is informed."), 0,
         "With 'neither... nor', the verb agrees with the nearer subject ('members'), and 'neither' pairs with 'nor'."),
        ("medium", "Fill in the blank: The report must be submitted ___ Friday, 5 PM.", ("by", "until", "since", "at"), 0,
         "'By' marks a deadline; 'until' describes something continuing up to a time."),
        ("medium", "Choose the passive voice of: \"The team completed the migration.\"",
         ("The migration was completed by the team.", "The migration is completed by the team.",
          "The migration has been completed by the team.", "The team was completed by the migration."), 0,
         "Simple past active ('completed') becomes 'was completed' in the passive."),
        ("medium", "What does the idiom 'to burn the midnight oil' mean?",
         ("To work or study late into the night", "To waste resources", "To start a conflict", "To finish work early"), 0,
         "It describes working late, originally by lamplight."),
        ("hard", "Choose the word that best completes: \"His explanation was so ___ that even experts struggled to follow it.\"",
         ("convoluted", "lucid", "succinct", "transparent"), 0, "Convoluted means extremely complex and hard to follow; the other options mean clear."),
        ("hard", "Select the correctly punctuated sentence.",
         ("The project, which started in May, is now complete.", "The project which started in May, is now complete.",
          "The project, which started in May is now complete.", "The project which, started in May, is now complete."), 0,
         "A non-restrictive clause needs a comma on both sides."),
        ("hard", "Choose the sentence that is most concise without losing meaning.",
         ("We will decide after reviewing the data.", "We will make a decision after we have done a review of the data.",
          "After the data has been reviewed by us, a decision will be made.", "A decision will be made by us after a data review."), 0,
         "Active voice with strong verbs ('decide', 'reviewing') says the same thing in the fewest words."),
    ],
}

VERBAL_TOPIC = {"label": "Verbal Ability", "keywords": (), "questions": EXTRA_QUESTIONS["verbal"]}
