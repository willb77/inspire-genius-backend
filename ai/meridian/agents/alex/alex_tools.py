from __future__ import annotations

from typing import Any, Optional
from enum import Enum
from pydantic import BaseModel, Field
from prism_inspire.core.log_config import logger


# ------------------------------------------------------------------
# Constants
# ------------------------------------------------------------------

PRISM_MIN_AGE = 13  # PRISM available from 8th grade / age 13-14

# Minimum grade level for PRISM eligibility (8th grade)
PRISM_MIN_GRADE = 8


# ------------------------------------------------------------------
# Models
# ------------------------------------------------------------------

class AgeGroup(str, Enum):
    MIDDLE_SCHOOL = "middle_school"
    HIGH_SCHOOL = "high_school"
    UNIVERSITY = "university"
    GRADUATE = "graduate"


class CareerExploration(BaseModel):
    """Age-appropriate career exploration results."""
    student_id: str
    age_group: AgeGroup
    career_families: list[str] = Field(default_factory=list)
    exploration_activities: list[str] = Field(default_factory=list)
    next_steps: list[str] = Field(default_factory=list)
    prism_eligible: bool = False


class AcademicPlan(BaseModel):
    """Academic planning recommendations."""
    student_id: str
    goals: list[str] = Field(default_factory=list)
    recommended_courses: list[str] = Field(default_factory=list)
    study_strategies: list[str] = Field(default_factory=list)
    grade_level: str = ""


# ------------------------------------------------------------------
# Career family mappings by PRISM preference
# ------------------------------------------------------------------

CAREER_FAMILIES_BY_PREFERENCE: dict[str, dict[str, list[str]]] = {
    "gold": {
        "middle_school": [
            "Science & Research",
            "Building & Engineering",
            "Medicine & Health",
        ],
        "high_school": [
            "Healthcare & Medical Sciences",
            "Engineering & Architecture",
            "Accounting & Finance",
            "Quality Assurance & Compliance",
        ],
        "university": [
            "Operations Management",
            "Financial Analysis & Accounting",
            "Healthcare Administration",
            "Engineering & Technical Management",
            "Compliance & Risk Management",
        ],
        "graduate": [
            "Executive Operations Leadership",
            "Clinical Research & Practice",
            "Systems Engineering",
            "Regulatory Strategy",
        ],
    },
    "green": {
        "middle_school": [
            "Helping & Teaching",
            "Art & Creativity",
            "Working with Animals",
        ],
        "high_school": [
            "Education & Training",
            "Counseling & Social Work",
            "Human Resources",
            "Nonprofit & Community Development",
        ],
        "university": [
            "Human Resources & Talent Development",
            "Education & Instructional Design",
            "Clinical Psychology & Counseling",
            "Customer Success & Client Relations",
            "Community & Social Impact",
        ],
        "graduate": [
            "Organizational Development",
            "Executive Coaching",
            "Educational Leadership",
            "Social Enterprise",
        ],
    },
    "blue": {
        "middle_school": [
            "Computers & Technology",
            "Math & Puzzles",
            "Space & Discovery",
        ],
        "high_school": [
            "Data Science & Analytics",
            "Computer Science & Software",
            "Research & Development",
            "Strategic Consulting",
        ],
        "university": [
            "Data Science & Machine Learning",
            "Strategic Consulting",
            "Product Management",
            "Research & Development",
            "Investment Analysis",
        ],
        "graduate": [
            "Chief Strategy & Analytics Roles",
            "AI & Advanced Research",
            "Venture Capital & Private Equity",
            "Academic Research",
        ],
    },
    "red": {
        "middle_school": [
            "Sports & Competition",
            "Business & Selling",
            "Adventure & Travel",
        ],
        "high_school": [
            "Entrepreneurship & Startups",
            "Sales & Business Development",
            "Marketing & Media",
            "Sports Management",
        ],
        "university": [
            "Entrepreneurship & Venture Creation",
            "Sales Leadership",
            "Marketing & Brand Management",
            "Business Development",
            "Emergency & Crisis Management",
        ],
        "graduate": [
            "Executive Leadership & CEO Track",
            "Startup Founding",
            "Mergers & Acquisitions",
            "Turnaround Management",
        ],
    },
}

# Generic career families when no PRISM data is available
GENERIC_CAREER_FAMILIES: dict[str, list[str]] = {
    "middle_school": [
        "Science & Discovery",
        "Art & Creativity",
        "Helping People",
        "Technology & Computers",
        "Building & Making Things",
        "Sports & Movement",
    ],
    "high_school": [
        "STEM (Science, Technology, Engineering, Math)",
        "Business & Entrepreneurship",
        "Healthcare & Medicine",
        "Education & Social Services",
        "Creative Arts & Design",
        "Trades & Technical Skills",
    ],
    "university": [
        "Technology & Innovation",
        "Business & Finance",
        "Healthcare & Life Sciences",
        "Education & Development",
        "Creative Industries",
        "Public Service & Policy",
    ],
    "graduate": [
        "Executive Leadership",
        "Advanced Research & Innovation",
        "Professional Services",
        "Social Impact & Policy",
        "Entrepreneurship",
    ],
}


# ------------------------------------------------------------------
# Pure functions
# ------------------------------------------------------------------

def is_prism_eligible(age_or_grade: int) -> bool:
    """
    Check if a student is eligible for PRISM assessment.

    Returns True if age >= 13 or grade >= 8.

    Pure function: no side effects, fully testable.
    """
    # If the value looks like a grade (1-12), check against grade minimum
    if 1 <= age_or_grade <= 12:
        return age_or_grade >= PRISM_MIN_GRADE
    # Otherwise treat as age
    return age_or_grade >= PRISM_MIN_AGE


def explore_careers(
    interests: list[str],
    behavioral_context: Optional[dict[str, Any]] = None,
    age_group: str = "middle_school",
    student_id: str = "",
) -> CareerExploration:
    """
    Generate age-appropriate career family recommendations.

    Uses PRISM behavioral context when available and eligible;
    falls back to interest-based exploration for younger students.

    Pure function: no side effects, fully testable.
    """
    effective_age_group = AgeGroup(age_group) if age_group in AgeGroup.__members__.values() else AgeGroup.MIDDLE_SCHOOL
    prism_eligible = effective_age_group != AgeGroup.MIDDLE_SCHOOL

    # Determine career families
    career_families: list[str] = []
    if behavioral_context and prism_eligible:
        primary = behavioral_context.get("primary_preference", "")
        secondary = behavioral_context.get("secondary_preference", "")

        primary_families = CAREER_FAMILIES_BY_PREFERENCE.get(
            primary, {}
        ).get(effective_age_group.value, [])
        secondary_families = CAREER_FAMILIES_BY_PREFERENCE.get(
            secondary, {}
        ).get(effective_age_group.value, [])

        # Primary families first, then add unique secondary
        career_families = list(primary_families)
        for fam in secondary_families:
            if fam not in career_families:
                career_families.append(fam)
    else:
        career_families = list(
            GENERIC_CAREER_FAMILIES.get(effective_age_group.value, [])
        )

    # Build exploration activities by age group
    activities: dict[str, list[str]] = {
        "middle_school": [
            "Try a career exploration quiz online",
            "Interview a family member about their job",
            "Join a club related to your interests",
            "Watch videos about different careers",
            "Try a new hobby that connects to a career area",
        ],
        "high_school": [
            "Job shadow someone in a field that interests you",
            "Take an elective in a new subject area",
            "Volunteer or do community service in a relevant area",
            "Start a side project or small business",
            "Attend a college or career fair",
        ],
        "university": [
            "Apply for internships in target career families",
            "Conduct informational interviews with professionals",
            "Build a portfolio or personal website",
            "Join professional organizations as a student member",
            "Attend industry conferences or networking events",
        ],
        "graduate": [
            "Develop a professional brand and thought leadership",
            "Build strategic relationships in your target industry",
            "Seek advisory or board positions for experience",
            "Publish or present in your area of expertise",
            "Negotiate your first post-graduation role strategically",
        ],
    }

    exploration_activities = activities.get(effective_age_group.value, activities["middle_school"])

    # Build next steps
    next_steps: list[str] = []
    if interests:
        next_steps.append(
            f"You mentioned interest in: {', '.join(interests)}. "
            "Let's explore careers that connect to these interests."
        )
    if not behavioral_context and prism_eligible:
        next_steps.append(
            "A PRISM behavioral assessment could help us personalize "
            "career recommendations to your natural strengths."
        )
    next_steps.append("Pick one career family above and research it this week.")

    logger.info(
        f"Meridian: career exploration for student {student_id} "
        f"(age_group={effective_age_group.value}, "
        f"prism={'yes' if behavioral_context and prism_eligible else 'no'})"
    )

    return CareerExploration(
        student_id=student_id,
        age_group=effective_age_group,
        career_families=career_families,
        exploration_activities=exploration_activities,
        next_steps=next_steps,
        prism_eligible=prism_eligible,
    )


def build_academic_plan(
    goals: list[str],
    grade_level: str = "",
    student_id: str = "",
) -> AcademicPlan:
    """
    Build an academic plan with study strategies and course recommendations.

    Pure function: no side effects, fully testable.
    """
    # Study strategies by education level
    strategy_map: dict[str, list[str]] = {
        "middle_school": [
            "Use a planner to track assignments and due dates",
            "Break big projects into smaller steps",
            "Study in short focused sessions (25 minutes on, 5 minutes off)",
            "Ask questions in class — curiosity is a superpower",
            "Find a study buddy for subjects that feel hard",
        ],
        "high_school": [
            "Create a weekly study schedule and stick to it",
            "Use active recall — quiz yourself instead of re-reading",
            "Take practice tests under timed conditions",
            "Form or join a study group for challenging courses",
            "Connect with teachers during office hours for extra help",
        ],
        "university": [
            "Use spaced repetition for long-term retention",
            "Build relationships with professors in your major",
            "Balance course load with internship and extracurricular goals",
            "Use campus career services for resume and interview prep",
            "Develop time management systems that work for your style",
        ],
        "graduate": [
            "Prioritize depth over breadth in your area of focus",
            "Build a professional network alongside academic work",
            "Seek research or teaching opportunities for career positioning",
            "Develop writing and presentation skills as career assets",
            "Balance academic demands with self-care and sustainability",
        ],
    }

    # Determine level from grade_level string
    level = "middle_school"
    grade_lower = grade_level.lower()
    if any(term in grade_lower for term in ["university", "college", "undergrad"]):
        level = "university"
    elif any(term in grade_lower for term in ["graduate", "masters", "phd", "doctoral"]):
        level = "graduate"
    elif any(term in grade_lower for term in ["high", "9", "10", "11", "12"]):
        level = "high_school"

    study_strategies = strategy_map.get(level, strategy_map["middle_school"])

    # Course recommendations based on goals
    recommended_courses: list[str] = []
    for goal in goals:
        goal_lower = goal.lower()
        if any(term in goal_lower for term in ["tech", "computer", "coding", "software"]):
            recommended_courses.append("Computer Science / Programming")
        elif any(term in goal_lower for term in ["business", "entrepreneur", "finance"]):
            recommended_courses.append("Business / Economics")
        elif any(term in goal_lower for term in ["health", "medical", "doctor", "nurse"]):
            recommended_courses.append("Biology / Health Sciences")
        elif any(term in goal_lower for term in ["art", "design", "creative"]):
            recommended_courses.append("Art / Design Fundamentals")
        elif any(term in goal_lower for term in ["write", "communicate", "journal"]):
            recommended_courses.append("English / Communications")
        elif any(term in goal_lower for term in ["lead", "manage", "team"]):
            recommended_courses.append("Leadership / Organizational Behavior")

    if not recommended_courses:
        recommended_courses.append("Explore electives across different areas to discover new interests")

    logger.info(
        f"Meridian: built academic plan for student {student_id} "
        f"(level={level}, {len(goals)} goals)"
    )

    return AcademicPlan(
        student_id=student_id,
        goals=goals,
        recommended_courses=recommended_courses,
        study_strategies=study_strategies,
        grade_level=grade_level,
    )
