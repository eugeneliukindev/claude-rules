from resumes.grading import grade_of


def test_senior_beats_junior() -> None:
    assert grade_of("Senior engineer, mentored juniors") == "senior"
