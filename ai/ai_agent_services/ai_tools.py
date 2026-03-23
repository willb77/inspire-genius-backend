from typing import List, Optional

from pydantic import BaseModel, Field

user_document_queries_description=(
            "Queries for searching specific files uploaded by the user (PRISM Reports, Resumes, Notes). "
            "TRIGGER: Populate this field if the user uses possessives ('my', 'our', 'his', 'her', 'this', 'these') OR mentions artifacts ('report', 'profile', 'map'). "
            "ACTION: Extract the specific behavior, trait, or pattern the user is asking about. "
            "logic: If the input is 'my opposite behaviours', the search phrase is 'opposite behaviours' because we need to find where that appears in the file."
            "this must return queries even if the user ask question about his own data. the files can be anything uploaded by the user like resume, prism report, notes, bills, diaries etc."
        )


class AssistantQuery(BaseModel):
    """
    A Pydantic model to classify and structure various professional user queries for an AI assistant.
    """

    refined_query: List[str] = Field(
        ...,
        max_items=3,
        description=user_document_queries_description,
    )


class PRISMAssistantQuery(BaseModel):
    """
    Analyzes user input to populate search queries for three distinct databases.
    """

    user_document_queries: List[str] = Field(
        default=[],
        max_items=2,
        description=user_document_queries_description,
    )

    prism_knowledge_queries: List[str] = Field(
        default=[],
        max_items=3,
        description=(
            "Queries for the Core PRISM Technical Manual. "
            "TRIGGER: Populate this field if the query involves PRISM terminology, map mechanics, or behavioral patterns. "
            "REQUIRED TOPICS: "
            "1. The 4 Colors and 8 Dimensions. "
            "2. Map mechanics: 'Opposite behaviours', 'Shadow', 'Mirror', 'Consistency'. "
            "3. 'Overdone Strengths'. "
            "4. Meaning of specific scores or intensity. "
            "Logic: Even if the user asks about 'my opposite behaviours', you must query this field to retrieve the theoretical definition of what an opposite behavior actually is."
        )
    )

    prism_coach_professional_knowledge: List[str] = Field(
        default=[],
        max_items=3,
        description=(
            "Queries for the External Professional Library (General Psychology). "
            "TRIGGER: Populate this field ONLY for broad psychological frameworks not specific to the PRISM map structure. "
            "REQUIRED TOPICS: "
            "1. Emotional Intelligence (EQ). "
            "2. Mental Toughness. "
            "3. The Big Five. "
            "4. Neuroplasticity / Neuroscience. "
            "5. General Psychology in Business/Sport. "
            "EXCLUSION: 'Opposite behaviours' is a PRISM map mechanic, so it belongs in prism_knowledge_queries, NOT here."
        )
    )


class OtherAgentContactQuery(BaseModel):
    """
    A Pydantic model to identify if a user query involves contacting another agent.
    """
    agent_id : Optional[str] = Field(
        default=None,
        description=(
            "The unique identifier of the other agent to contact"
            )
    )
    agent_name : Optional[str] = Field(
        default=None,
        description=(
            "The name of the other agent to contact"
            )
    )
    agent_query : Optional[str] = Field(
        default=None,
        description=(
            "The optimised query to be sent to the other agent so that it can provide the best possible response."
            )
    )



class CareerAssistantQuery(BaseModel):
    """
    A Pydantic model to classify and structure various career-related user queries for an AI assistant.
    """
    is_agent_contact_query: bool = Field(
        default=False,
        description=(
        "Based on the user Input, set to True if the user is requesting to contact another agent for assistance or information depending on the agent list. Only set to True if the user is requesting to contact another agent for assistance or information depending on the agent list"
        )
    )
    agent_contact_query: Optional[OtherAgentContactQuery] = Field(
        default=None,
        description=(
            "If is_agent_contact_query is True, populate this field with the details of the agent to contact"
        )
    )
    user_document_queries: List[str] = Field(
        default=[],
        max_items=3,
        description=user_document_queries_description,
    )


# Extra's
other_user_information: bool = Field(
    default=False,
    description=(
        "Set to True if the query asks for professional information about another person, compares individuals, or inquires about a professional interaction involving another person. "
        "This must be True even if the query includes the user (e.g., 'me', 'I'), as long as another specific person is a subject of the query."
    ),
)
target_users: Optional[List[str]] = Field(
    default=None,
    description=(
        "A list of all specific usernames or full names who are the subject of the query. "
        "Extract all mentioned names. If the user is being compared to someone, include that person's name. "
        "Example 1: In 'How is Jane's performance?', extract ['Jane']. "
        "Example 2: In 'Compare my skills with David's', extract ['David']."
    ),
)
