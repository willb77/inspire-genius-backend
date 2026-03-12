from datetime import date
from typing import Dict, List, Optional, Union
from uuid import UUID

from pydantic import BaseModel, Field
import toon

class GETCategoryID(BaseModel):
    category_id: UUID = Field(..., description="The unique uuid identifier of the category.")
    name : str = Field(..., description="The name of the category.")
    filename: str = Field(..., description="The name of the file. The name should be in sentence case without extensions. Take the actual filename for reference.")


class PersonalInfo(BaseModel):
    """Details identifying the subject of the report."""

    name: str = Field(..., description="Full name of the candidate.")
    company: str = Field(..., description="Company or context for the report.")


class ReportMetadata(BaseModel):
    """Contextual information about the report itself."""

    inventory_date: str = Field(..., description="Date when the inventory was created. The date should be readable format. E.g., 'March 15, 2023'.")
    report_date: str = Field(..., description="Date when the report was generated. The date should be readable format. E.g., 'March 20, 2023'.")


class QuadrantValues(BaseModel):
    """Represents the four quadrant values for a single row."""

    underlying: int
    adapted: Optional[int] = None
    consistent: Optional[int] = None
    blueprint: Optional[int] = None


class DimensionScores(BaseModel):
    """Represents the scores for a single dimension."""

    underlying: int
    adapted: Optional[int] = None
    consistent: Optional[int] = None


class AllDimensionValues(BaseModel):
    """Represents the scores for all dimensions."""

    inn: DimensionScores = Field(..., alias="Innovation")
    init: DimensionScores = Field(..., alias="Initiative")
    sup: DimensionScores = Field(..., alias="Support")
    co: DimensionScores = Field(..., alias="Coordination")
    foc: DimensionScores = Field(..., alias="Focus")
    del_val: DimensionScores = Field(..., alias="Delivery")
    fin: DimensionScores = Field(..., alias="Finishing")
    eval_val: DimensionScores = Field(..., alias="Evaluation")


class IntroversionExtroversion(BaseModel):
    """
    Represents the introversion/extroversion classification.
    These are located in the graph at the bottom right of the report.
    """
    introversion: int = Field(..., description="The introversion score.")
    extroversion: int = Field(..., description="The extroversion score.")


# --- Global Mappings and Behavioral Data ---
DIMENSION_MAP: Dict[str, Dict[str, str]] = {
    "inn": {"name": "Innovating", "quadrant": "Expression"},
    "init": {"name": "Initiating", "quadrant": "Expression"},
    "sup": {"name": "Supporting", "quadrant": "Stability"},
    "co": {"name": "Coordinating", "quadrant": "Stability"},
    "foc": {"name": "Focusing", "quadrant": "Drive"},
    "del_val": {"name": "Delivering", "quadrant": "Drive"},
    "fin": {"name": "Finishing", "quadrant": "Analysis"},
    "eval_val": {"name": "Evaluating", "quadrant": "Analysis"},
}

QUADRANT_INFO: Dict[str, str] = {
    "Expression": "Green",
    "Stability": "Blue",
    "Drive": "Red",
    "Analysis": "Gold",
}

QUADRANT_KEYWORDS: Dict[str, List[str]] = {
    "Analysis": [
        "Cautious",
        "Methodical",
        "Precise",
        "Thorough",
        "Analytical",
        "Shrewd",
    ],
    "Expression": [
        "Inspiring",
        "Creative",
        "Imaginative",
        "Persuasive",
        "Optimistic",
        "Lively",
    ],
    "Stability": [
        "Kind",
        "Patient",
        "Caring",
        "Co-operative",
        "Dependable",
        "Supportive",
    ],
    "Drive": [
        "Forceful",
        "Decisive",
        "Hard-driving",
        "Demanding",
        "Challenging",
        "Competitive",
    ],
}

TRANSITIONAL_STYLES: Dict[str, str] = {
    "Deciding": "Analysis/Expression",
    "Realistic": "Analysis/Drive",
    "Processing": "Drive/Stability",
    "Idealistic": "Expression/Stability",
}

DIMENSION_KEY_POINTS: Dict[str, Dict] = {
    "Innovating": {
        "natural_strengths": [
            "Imaginative, innovative thinker.",
            "Generates ideas and concepts.",
            "Visualises outcomes.",
            "Creates original solutions.",
            "Unorthodox, fertile-minded and radical.",
        ],
        "potential_weaknesses_if_overdone": [
            "Low attention to detail.",
            "Has difficulty explaining own ideas.",
            "Absent minded and forgetful.",
            "Dislikes criticism and following rules.",
            "Can be wayward and independent.",
        ],
        "low_preference_behaviours": "Less likely to be naturally innovative and imaginative, or to produce radical solutions. Will be less comfortable working without guidelines or rules and will occasionally show a need for accuracy and detail.",
    },
    "Initiating": {
        "natural_strengths": [
            "Outgoing, animated and entertaining.",
            "Articulate and persuasive.",
            "Establishes rapport easily.",
            "High-spirited, jovial and light-hearted.",
            "Good at achieving 'win-win' negotiations.",
        ],
        "potential_weaknesses_if_overdone": [
            "Over optimistic and unrealistic.",
            "Fails to follow through or deliver.",
            "Easily bored and distracted.",
            "Need to be entertaining and popular.",
            "Makes impetuous, intuitive decisions.",
        ],
        "low_preference_behaviours": "Less likely to be naturally animated, high-spirited, or easily bored. Will be less excited by change and will occasionally show a need to question the accuracy and validity of information before deciding.",
    },
    "Supporting": {
        "natural_strengths": [
            "Kind hearted, harmonious and caring.",
            "Supportive of others.",
            "Handles repetitive or routine work well.",
            "Good natured and accommodating.",
            "Considerate, kindly and compassionate.",
        ],
        "potential_weaknesses_if_overdone": [
            "Dislikes conflict and aggressive people.",
            "Unassertive and over sensitive.",
            "Uncomfortable making tough decisions.",
            "Dislikes pressure or fast pace.",
            "Uncomfortable with change.",
        ],
        "low_preference_behaviours": "Less likely to be naturally supportive of others, or to accommodate their needs. Will be less comfortable with routine work and will occasionally show a need to be assertive, outspoken and challenging.",
    },
    "Coordinating": {
        "natural_strengths": [
            "Makes good use of other people's skills.",
            "Encourages opinions and participation.",
            "Broad minded and collaborative.",
            "Remains calm when under pressure.",
            "Consultative and open-minded.",
        ],
        "potential_weaknesses_if_overdone": [
            "Lacks drive and independence of mind.",
            "Relies heavily on gaining agreement.",
            "Laid-back and casual.",
            "Can appear detached and laid back.",
            "Too tolerant of inappropriate behaviour.",
        ],
        "low_preference_behaviours": "Less likely to involve others or to seek their opinions or participation. Will be less comfortable delegating to others and will occasionally show a need to be independent, self-reliant and determined.",
    },
    "Focusing": {
        "natural_strengths": [
            "Blunt, outspoken, forceful and dominant.",
            "Authoritative, assertive and challenging.",
            "Copes well with adverse conditions.",
            "Driven to win and achieve status.",
            "High pressure negotiating skills.",
        ],
        "potential_weaknesses_if_overdone": [
            "Irritable and easily frustrated.",
            "Provocative and argumentative.",
            "Poor listener when under pressure.",
            "Suspicious of the motives of others.",
            "Quick to anger and volatile.",
        ],
        "low_preference_behaviours": "Less likely to be forceful, outspoken or driven to achieve personal goals. Will be less comfortable in tough conditions and will occasionally show a need for harmony and routine work at a steady pace.",
    },
    "Delivering": {
        "natural_strengths": [
            "Self-reliant and venturesome.",
            "Independent and self-motivated.",
            "Practical, determined and competitive.",
            "Works well when under pressure.",
            "Likes structure and organisation.",
        ],
        "potential_weaknesses_if_overdone": [
            "Can be over-competitive for status.",
            "Inflexible and single-minded.",
            "Uncomfortable with sudden change.",
            "Frustrated by others' low commitment.",
            "Insensitive to others' emotional needs.",
        ],
        "low_preference_behaviours": "Less likely to be self-reliant, independent or competitive. Will be less comfortable working under pressure and will occasionally show a need to consult others, delegate and be open-minded.",
    },
    "Finishing": {
        "natural_strengths": [
            "Strong attention to detail and accuracy.",
            "Conscientious, painstaking and orderly.",
            "Good at communicating complex data.",
            "Focuses on accuracy and high standards.",
            "Follows tasks through to completion.",
        ],
        "potential_weaknesses_if_overdone": [
            "Insular, pedantic and slow moving.",
            "Dislikes delegating to others.",
            "Uneasy making contact with strangers.",
            "Intolerant of errors or disorganisation.",
            "Prone to worrying unduly or anxiety.",
        ],
        "low_preference_behaviours": "Less likely to be attentive to detail, thorough or conscientious. Will be less comfortable following strict rules and will occasionally show a need to be imaginative and find radical solutions to problems.",
    },
    "Evaluating": {
        "natural_strengths": [
            "Questions the validity of data.",
            "Checks the pros and cons of all options.",
            "Does not accept things at face value.",
            "Makes astute decisions based on facts.",
            "Fair-minded and unemotional.",
        ],
        "potential_weaknesses_if_overdone": [
            "May be seen as sceptical and cynical.",
            "Can be uninspiring and negative.",
            "Appears indifferent to others' feelings.",
            "Slow and cautious when deciding.",
            "Unreceptive to new, untried ideas.",
        ],
        "low_preference_behaviours": "Less likely to be cautious, logical or sceptical. Will be less comfortable being unemotional and will occasionally show a need to be intuitive and to experience new activities and new acquaintances.",
    },
}

AXIS_KEY_POINTS: Dict[str, Dict[str, List[str]]] = {
    "Dynamic Axis": {
        "traits": [
            "Seeks opportunities/challenges; takes risks.",
            "Highly adaptable; changes course quickly.",
            "Good communicator; connects effectively.",
            "Prefers high activity, excitement, change.",
            "Optimistic, energetic, positive; avoids negativity.",
            "Learns by doing; projects confidence.",
            "Future-oriented; reaches conclusions quickly.",
            "High enthusiasm, low patience; dislikes routine.",
        ]
    },
    "Discerning Axis": {
        "traits": [
            "Detail-oriented; makes thoughtful decisions.",
            "Well-developed judgment; separates fact from opinion.",
            "Considers outcomes; avoids impulsiveness.",
            "Prefers stable, calm, steady pace.",
            "Focuses on tasks; favors routine over energy bursts.",
            "Cautious; considers long-term effects.",
            "Strong critical thinking; identifies problems.",
            "High patience, low enthusiasm; works steadily.",
        ]
    },
    "Task-Oriented Axis": {
        "traits": [
            "Values logic over sentiment; truthful rather than tactful.",
            "Strong administrative abilities; questions conclusions.",
            "Brief and businesslike; can be insensitive.",
            "Functions without harmony; makes impersonal decisions.",
            "Focuses on facts over feelings; firm-minded.",
            "Comfortable with ideas; guards emotions.",
            "Lives by a plan; decisive; goal-oriented.",
            "Needs fairness; structures life based on facts.",
        ]
    },
    "People-Oriented Axis": {
        "traits": [
            "High-touch and relationship-focused.",
            "Values sentimental traditions; tactful; strong social abilities.",
            "Accepts conclusions; talkative and friendly.",
            "Desires harmony; sensitive to others' feelings.",
            "Decides based on others; prefers feelings over facts.",
            "Sympathetic, flexible, comfortable with people.",
            "Expresses emotions openly; lives in the moment.",
            "More curious than decisive; enjoys starting projects.",
            "Needs appreciation and praise.",
        ]
    },
}

OPPOSITE_PAIRS = [
    ("inn", "fin"),
    ("init", "eval_val"),
    ("sup", "foc"),
    ("co", "del_val"),
]


def get_behavioral_analysis(dimension_name: str, score: int) -> List[str]:
    """Determines behavioral traits based on the 'Underlying' score."""
    points = DIMENSION_KEY_POINTS.get(dimension_name, {})
    analysis = []
    if score >= 75:
        analysis.append(
            "Potential weaknesses if overdone: "
            + " ".join(points.get("potential_weaknesses_if_overdone", []))
        )
    if score >= 65:
        analysis.append(
            "Natural strengths: " + " ".join(points.get("natural_strengths", []))
        )
    if score <= 35:
        analysis.append(
            "Low preference behaviours: " + points.get("low_preference_behaviours", "")
        )
    return analysis


class PrismReport(BaseModel):
    """The main model for the PRISM assessment report."""

    personal_info: PersonalInfo
    metadata: ReportMetadata
    dimension_values: AllDimensionValues = Field(
        ..., description="Values for all dimensions. Second table in the right column."
    )
    introversion_extroversion: IntroversionExtroversion = Field(
        ...,
        description="Values for the introversion-extroversion dimension. Last table in the right column.",
    )

    @property
    def quadrant_values(self) -> List[QuadrantValues]:
        dim = self.dimension_values
        
        def avg(v1, v2):
            if v1 is None or v2 is None: return None
            return int(round((v1 + v2) / 2))

        # Expression: Innovation + Initiative
        exp_u = avg(dim.inn.underlying, dim.init.underlying)
        exp_a = avg(dim.inn.adapted, dim.init.adapted)
        exp_c = avg(dim.inn.consistent, dim.init.consistent)
        
        # Stability: Support + Coordination
        stab_u = avg(dim.sup.underlying, dim.co.underlying)
        stab_a = avg(dim.sup.adapted, dim.co.adapted)
        stab_c = avg(dim.sup.consistent, dim.co.consistent)
        
        # Drive: Delivery + Focus
        drive_u = avg(dim.del_val.underlying, dim.foc.underlying)
        drive_a = avg(dim.del_val.adapted, dim.foc.adapted)
        drive_c = avg(dim.del_val.consistent, dim.foc.consistent)
        
        # Analysis: Finishing + Evaluation
        anal_u = avg(dim.fin.underlying, dim.eval_val.underlying)
        anal_a = avg(dim.fin.adapted, dim.eval_val.adapted)
        anal_c = avg(dim.fin.consistent, dim.eval_val.consistent)
        
        return [
            QuadrantValues(underlying=exp_u, adapted=exp_a, consistent=exp_c),
            QuadrantValues(underlying=stab_u, adapted=stab_a, consistent=stab_c),
            QuadrantValues(underlying=drive_u, adapted=drive_a, consistent=drive_c),
            QuadrantValues(underlying=anal_u, adapted=anal_a, consistent=anal_c)
        ]

    # --- Formatting Helpers ---

    def _fmt(self, score: Union[int, float, None]) -> Optional[str]:
        """Formats score as '85 (Very High)' for token efficiency."""
        if score is None: return None
        
        if score >= 75: label = "Very High"
        elif score >= 65: label = "Natural"
        elif score >= 50: label = "Moderate"
        elif score >= 36: label = "Low Mod"
        else: label = "Very Low"
        
        return f"{score} ({label})"

    def _format_scores(self, scores_obj) -> str:
        """Helper method to format scores consistently."""
        scores_parts = [f"Underlying:{self._fmt(scores_obj.underlying)}"]
        if scores_obj.adapted is not None:
            scores_parts.append(f"Adapted:{self._fmt(scores_obj.adapted)}")
        if scores_obj.consistent is not None:
            scores_parts.append(f"Consistent:{self._fmt(scores_obj.consistent)}")
        return ", ".join(scores_parts)

    def _build_header(self) -> List[str]:
        """Build the header section of the report."""
        info = self.personal_info
        return [
            f"###Section: Map PRISM Profile: {info.name} ({info.company}) | {self.metadata.report_date} ###"
        ]

    def _build_quadrant_summaries(self) -> List[str]:
        """Build the quadrant summaries section."""
        prompt_parts = ["\n#### 4 Quadrants"]
        quadrant_names = list(QUADRANT_INFO.keys())

        for i, quad_data in enumerate(self.quadrant_values):
            name = quadrant_names[i]
            scores_str = self._format_scores(quad_data)
            prompt_parts.append(f"- {name} ({QUADRANT_INFO[name]}): ({scores_str})")

        string_prompt = "\n".join(prompt_parts)
        return string_prompt

    def _build_dimension_analysis(self) -> List[str]:
        """Build the dimension analysis section."""
        prompt_parts = ["\n### All 8 Behaviour Preference Dimensions"]
        prompt_parts.append("**Note: The following are the 8 behaviour preference dimensions. Do not miss any of the behaviours for insights.**")
        quadrant_names = list(QUADRANT_INFO.keys())

        # Group dimensions by quadrant
        dimensions_by_quadrant = {q: [] for q in quadrant_names}
        for key, data in DIMENSION_MAP.items():
            dimensions_by_quadrant[data["quadrant"]].append(key)

        for quadrant in quadrant_names:
            prompt_parts.extend(
                self._build_quadrant_section(quadrant, dimensions_by_quadrant[quadrant])
            )

        return prompt_parts

    def _build_quadrant_section(
        self, quadrant: str, dimension_keys: List[str]
    ) -> List[str]:
        """Build a single quadrant section with its dimensions."""
        keywords = ", ".join(QUADRANT_KEYWORDS[quadrant])
        section_parts = [f"\n##### {quadrant} (Traits: {keywords})"]

        for key in dimension_keys:
            section_parts.extend(self._build_dimension_entry(key))

        return section_parts

    def _build_dimension_entry(self, key: str) -> List[str]:
        """Build a single dimension entry with analysis."""
        scores_obj = getattr(self.dimension_values, key)
        name = DIMENSION_MAP[key]["name"]
        scores_str = self._format_scores(scores_obj)

        entry_parts = [f"- {name}: ({scores_str})"]

        analysis_lines = get_behavioral_analysis(name, scores_obj.underlying)
        for line in analysis_lines:
            entry_parts.append(f"  - {line}")
            
        return entry_parts


    def build_behaviour_summary(self) -> List[str]:
        """Categorise all 8 behaviours by underlying score level."""
        buckets = {
            "Very High": [],
            "Natural": [],
            "Moderate": [],
            "Low Mod": [],
            "Very Low": [],
        }
        for key, data in DIMENSION_MAP.items():
            score = getattr(self.dimension_values, key).underlying
            if score >= 75:
                label = "Very High"
            elif score >= 65:
                label = "Natural"
            elif score >= 50:
                label = "Moderate"
            elif score >= 36:
                label = "Low Mod"
            else:
                label = "Very Low"
            buckets[label].append(data["name"])

        parts = ["Behaviour Preference Overview"]
        for level, names in buckets.items():
            parts.append(f"- {level} Behaviour Preferences: {', '.join(names) if names else f'No {level} Behaviour preferences'}")
        return parts

    def build_opposite_behaviours(self):
        """
        Analyzes opposite behavior pairs and returns TOON ENCODED data.

        Opposite pairs: Innovating/Finishing, Initiating/Evaluating,
        Supporting/Focusing, Coordinating/Delivering.

        Having natural preferences for both behaviors in a pair does NOT
        create internal conflict. Application is situational — it is
        functionally impossible to apply both simultaneously, so one is
        used over the other depending on the work situation.

        Development strategy ("inhibit to inhabit"): To develop a target
        behavior when its opposite is natural-to-high (>=65), intentionally
        do less of the dominant opposite to create head-space for the brain
        to access and develop the target behavior.
        """
        results = []
        for k1, k2 in OPPOSITE_PAIRS:
            s1 = getattr(self.dimension_values, k1).underlying
            s2 = getattr(self.dimension_values, k2).underlying
            n1, n2 = DIMENSION_MAP[k1]["name"], DIMENSION_MAP[k2]["name"]

            if s1 >= 65 and s2 >= 65:
                status = "Behavioural Agility"
                desc = (
                    f"Natural preference for both {n1} and {n2}. "
                    f"Both behaviours are natural — application is situational. "
                    f"One will be utilised over the other depending on the "
                    f"specific work situation."
                )
            elif s1 >= 65 and s2 < 65:
                status = "Development Opportunity"
                desc = (
                    f"Natural-to-high {n1}. To develop {n2}, inhibit {n1} "
                    f"in specific work activities to create head-space "
                    f"(inhibit to inhabit)."
                )
            elif s2 >= 65 and s1 < 65:
                status = "Development Opportunity"
                desc = (
                    f"Natural-to-high {n2}. To develop {n1}, inhibit {n2} "
                    f"in specific work activities to create head-space "
                    f"(inhibit to inhabit)."
                )
            else:
                status = "Flexible"
                desc = (
                    f"Neither {n1} nor {n2} is dominant. "
                    f"No inhibition strategy needed."
                )

            results.append({
                "pair": f"{n1} ({self._fmt(s1)}) vs {n2} ({self._fmt(s2)})",
                "status": status,
                "desc": desc
            })

        return toon.encode({"opposite_behaviors": results})

    def _build_other_traits(self) -> List[str]:
        """Build the other traits section."""
        prompt_parts = ["\n#### Other Traits"]

        styles_str = "; ".join(
            [f"{style}: {desc}" for style, desc in TRANSITIONAL_STYLES.items()]
        )
        prompt_parts.append(f"- Transitional Styles: {styles_str}")

        ie = self.introversion_extroversion
        prompt_parts.append(
            f"- Introversion/Extroversion: Introversion: {self._fmt(ie.introversion)}, Extroversion: {self._fmt(ie.extroversion)}"
        )
        return prompt_parts

    def _build_axis(self) -> List[str]:
        """Build the axis scores section."""
        axis_parts = ["\n#### Axis Scores"]
        # Order: Expression(0), Stability(1), Drive(2), Analysis(3)
        expression = self.quadrant_values[0].underlying
        stability = self.quadrant_values[1].underlying
        drive = self.quadrant_values[2].underlying
        analysis = self.quadrant_values[3].underlying

        dynamic_axis = (drive + expression) / 2
        discerning_axis = (analysis + stability) / 2
        task_axis = (drive + analysis) / 2
        people_axis = (expression + stability) / 2

        axis_parts.extend([
            f"- Dynamic Axis: {self._fmt(dynamic_axis)}",
            f"- Discerning Axis: {self._fmt(discerning_axis)}",
            f"- Task-Oriented Axis: {self._fmt(task_axis)}",
            f"- People-Oriented Axis: {self._fmt(people_axis)}",
        ])

        if dynamic_axis >= 65:
            traits = AXIS_KEY_POINTS["Dynamic Axis"]["traits"]
            axis_parts.append(f"  - Dynamic Traits: {'; '.join(traits)}")

        if discerning_axis >= 65:
            traits = AXIS_KEY_POINTS["Discerning Axis"]["traits"]
            axis_parts.append(f"  - Discerning Traits: {'; '.join(traits)}")

        if task_axis >= 65:
            traits = AXIS_KEY_POINTS["Task-Oriented Axis"]["traits"]
            axis_parts.append(f"  - Task-Oriented Traits: {'; '.join(traits)}")

        if people_axis >= 65:
            traits = AXIS_KEY_POINTS["People-Oriented Axis"]["traits"]
            axis_parts.append(f"  - People-Oriented Traits: {'; '.join(traits)}")

        return "\n".join(axis_parts)

    def pstringify(self) -> str:
        """Converts the PRISM report into a concise, data-rich string for AI prompts."""
        prompt_parts = []
        prompt_parts.extend(self._build_header())
        prompt_parts.extend(self._build_dimension_analysis())
        # prompt_parts.extend(self._build_quadrant_summaries())
        prompt_parts.extend(self._build_other_traits())

        return "\n".join(prompt_parts)


class PrismDataSections(BaseModel):
    """
    Model containing all text-based sections to be extracted from data files.
    """
    work_apptitude_profile: Optional[str] = Field(None, description="Work Aptitude Profile")
    core_traits_profile: Optional[str] = Field(None, description="Core Traits Profile")
    work_preference_profile: Optional[str] = Field(None, description="Work Preference Profile")
    career_development_analysis: Optional[str] = Field(None, description="PRISM Career Development Analysis")
    emotional_intelligence_report: Optional[str] = Field(None, description="Emotional Intelligence Report (optional)")
    big_five_report: Optional[str] = Field(None, description="‘The Big Five’ Report (optional)")
    mental_toughness_report: Optional[str] = Field(None, description="Mental Toughness Report (optional)")


# --- PDF Mapping Model ---


class PageRange(BaseModel):
    start: int
    end: int


class PrismPdfMapping(BaseModel):
    is_prism_report: bool = Field(
        default=True,
        description="Is this pdf a PRISM report?. Change it to False if the contents appear to be not an prism report. ",
    )
    report_type: str = Field(
        ..., description="Type of PRISM report. in: 'PRISM Personal', 'PRISM Professional', 'PRISM Foundation'"
    )
    Map: PageRange = Field(
        ...,
        description="This will have Innovating, Initiating, Supporting, Coordinating, Focusing, Delivering. This is single page. (Single Page). Change the is_prism_report to False if these contents are not found. This will be single page.",
    )
    prism_profile_narrative: PageRange = Field(
        ..., description="Your PRISM Profile Narrative - 3"
    )
    work_preference_profile: PageRange = Field(
        ..., description="Work Preference Profile, - 5"
    )
    career_development_analysis: PageRange = Field(
        ..., description="PRISM Career Development Analysis - 6"
    )
    emotional_intelligence_report: Optional[PageRange] = Field(
        None, description="Emotional Intelligence Report (optional) - 8"
    )
    big_five_report: Optional[PageRange] = Field(
        None, description="‘The Big Five’ Report (optional) - 9"
    )
    mental_toughness_report: Optional[PageRange] = Field(
        None, description="Mental Toughness Report (optional) - 10"
    )


# --- AI Prompts for Vector Store Functions ---

narrative_prompt = """**Analyze the provided PRISM report images and extract all data.**

**1. For Graphs and Numerical Scores:**
Extract the exact values, scores, and percentages associated with every metric.
Explaination of scores if available should be converted into concise bullet points.
If the scores are represented in graphical format (charts or ranges), interpret the visual data to determine the precise numerical values.

**2. For Text, Explanations, and Paragraphs:**
Convert the content into concise, high-density facts. Remove conversational filler words (like "The report suggests," "It can be seen that") but strictly retain all specific adjectives, behavioral traits, feedback, and insights provided.

**Constraint:** Ensure every extracted sentence or bullet point explicitly names the specific trait or category it refers to so the context is preserved for data retrieval. Do not omit any data points."""


Splitter_prompt = """"
You are given the extraction of the pdf. go throughh this menu. Look at the Section Numbers
PRISM Report Contents:
SECTION 1.  Introduction
• How can PRISM help me?
• Why is PRISM different?
• Interpreting your PRISM Report
SECTION 2.  Personal Profile
• Your PRISM 8-Dimensional Map
• Dimension Key Points
SECTION 3.  Your PRISM Profile Narrative - Full
SECTION 4.  Benchmark vs. Candidate Comparison [Not requested]
SECTION 5.  Work Preference Profile
• Work Preference Profile
• Work Aptitude Overview
• Work Environment - Performance Predictions
SECTION 6.  PRISM Quadrant Colour Characteristics
SECTION 7.  PRISM Career Development Analysis
SECTION 8.  Emotional Intelligence Report
SECTION 9.   'The Big Five ' Report
SECTION 10.  Mental Toughness Report

Locate each section header by finding its section number (1 -10) on its first page.
1.In the raw text, the section number may appear alone on a line (either at the start or middle).
2.Near that number, you 'll find the report title written in ALL CAPS (e.g., 'PERSONAL', 'PROFESSIONAL', 'FOUNDATION', 'EDUCATION'), either on the next line, one line above, or one line below.

Determine the page-range for each requested section:
1. Record the first and last page where that section 's content appears.
2. Sections not requested (e.g. “Benchmark vs. Candidate Comparison”) must be skipped entirely.

Special case  - Section 2 (Personal Profile):
1.The PRISM 8-Dimensional Map always spans a single page and does not display its section number.
2. Do not include “Dimension Key Points” page no  - it follows the map page but is not requested.

Note: For a single page report, the page range will always be the same (e.g. 1-1).
"""


# --- Other Sections Prompt for TOON Data Extraction ---

other_sections_prompt = """You are analyzing data in TOON (Token-Oriented Object Notation) format.

**IMPORTANT: Ignore any behavioral preferences or personality-related data.**

Extract ALL other relevant structured data from this TOON-formatted content and return it in a structured TOON format.

Focus on extracting:
- Personal/demographic information (names, companies, dates)
- Metadata and report information
- Scores and metrics (non-behavioral)
- Any additional structured data not related to behavioral preferences

Return the extracted data in clean, structured TOON format using:
- key: value syntax for simple values
- Indentation for nested objects
- [N,]{fields}: format for tabular arrays

Be comprehensive but concise. Include all relevant data points while excluding behavioral preference data."""


# --- Data Section Prompt ---

# --- Data Sections Prompt ---

data_sections_prompt = """You are analyzing data.

Your task is to extract and generate content for ALL the following sections:
1. Work Aptitude Profile
2. Core Traits Profile
3. Work Preference Profile
4. Career Development Analysis
5. Emotional Intelligence Report (if available)
6. The Big Five Report (if available)
7. Mental Toughness Report (if available)

Using ONLY the provided data:
1. Identify the relevant information corresponding to EACH section.
2. Do not specify scores, generate a nice summary for each section. Without skipping anything

Return the result as a structured JSON object matching the requested schema."""
