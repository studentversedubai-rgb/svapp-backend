"""Test type safety validation on RegisterRequest directly"""
import json, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.path.insert(0, ".")
from pydantic import ValidationError
from app.modules.auth.schemas import RegisterRequest

def test_case(label, data):
    print(f"\n{'='*60}")
    print(f"TEST: {label}")
    print(f"{'='*60}")
    try:
        req = RegisterRequest(**data)
        print(f"  [PASS] Validation passed: {req.model_dump(exclude_unset=True)}")
    except ValidationError as e:
        print(f"  [REJECTED] Caught {len(e.errors())} error(s):")
        for err in e.errors():
            field = " -> ".join(str(x) for x in err["loc"])
            print(f"     * {field}: {err['msg']}")

# TEST 1: All gibberish
test_case("All gibberish data", {
    "email": "not-an-email",
    "name": "123!!@#",
    "first_name": "x",
    "last_name": "$$$$",
    "student_id": "!!!",
    "nationality": "999",
    "university": "<<<>>>",
    "phone_number": "gibberish",
    "age": 5,
    "device_id": "ab",
    "avatar_url": "not-a-url"
})

# TEST 2: Valid data
test_case("Valid data (should PASS)", {
    "email": "test@university.edu",
    "name": "Ahmed Khan",
    "first_name": "Ahmed",
    "last_name": "Khan",
    "student_id": "STU-2026-001",
    "nationality": "Emirati",
    "university": "University of Dubai",
    "phone_number": "+971501234567",
    "age": 21,
    "device_id": "my-device-12345",
    "avatar_url": "https://example.com/pic.png"
})

# TEST 3: Numbers in name
test_case("Numbers in name (should REJECT)", {
    "email": "test@university.edu",
    "name": "John123",
    "first_name": "John123",
    "last_name": "Doe456",
})

# TEST 4: Age too low
test_case("Age = 5 (should REJECT)", {
    "email": "test@university.edu",
    "name": "John Doe",
    "first_name": "John",
    "last_name": "Doe",
    "age": 5,
})

# TEST 5: Age too high
test_case("Age = 200 (should REJECT)", {
    "email": "test@university.edu",
    "name": "John Doe",
    "first_name": "John",
    "last_name": "Doe",
    "age": 200,
})

# TEST 6: Bad phone format
test_case("Bad phone (no + prefix)", {
    "email": "test@university.edu",
    "name": "John Doe",
    "first_name": "John",
    "last_name": "Doe",
    "phone_number": "0501234567",
})

# TEST 7: Special chars in student_id
test_case("Special chars in student_id (should REJECT)", {
    "email": "test@university.edu",
    "name": "John Doe",
    "first_name": "John",
    "last_name": "Doe",
    "student_id": "STU@#$%",
})

# TEST 8: Names with apostrophes/hyphens (should pass)
test_case("O'Brien and Al-Farsi (should PASS)", {
    "email": "test@university.edu",
    "name": "Mary O'Brien",
    "first_name": "Mary",
    "last_name": "Al-Farsi",
})

# TEST 9: Whitespace-only name
test_case("Whitespace-only name (should REJECT)", {
    "email": "test@university.edu",
    "name": "   ",
    "first_name": "   ",
    "last_name": "   ",
})

print(f"\n{'='*60}")
print("ALL TESTS COMPLETE!")
print(f"{'='*60}")
