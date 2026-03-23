# Python Imports
import boto3
from datetime import datetime, timezone
from botocore.exceptions import ClientError

# Internal Imports
from prism_inspire.core.config import settings
from prism_inspire.core.log_config import logger


AWS_REGION = settings.LOCATION_AWS_REGION
TRACKER_NAME = settings.TRACKER_NAME
COLLECTION_NAME = settings.COLLECTION_NAME

location = boto3.client(
    "location", region_name=AWS_REGION,
    aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
    aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
    aws_session_token=settings.AWS_SESSION_TOKEN
)


def create_geofence_collection():
    try:
        location.create_geofence_collection(
            CollectionName=COLLECTION_NAME,
            Description="Geofence collection created by utility"
        )
        logger.info(f"Created geofence collection {COLLECTION_NAME}")
        return True
    except ClientError as e:
        if e.response["Error"]["Code"] == "ConflictException":
            logger.exception(f"Collection '{COLLECTION_NAME}' already exists.")
            return True
        else:
            logger.exception(f"Failed to create collection: {e}")
            return False


def put_geofence(geofence_id: str, polygon_coordinates: list):
    """
    polygon_coordinates: A list of linear rings (outer ring, optional
    inner holes). Each linear ring is a list of [longitude, latitude]
    points.

    Example:
    [[
        [-123.0, 45.0],
        [-123.0, 46.0],
        [-122.0, 46.0],
        [-122.0, 45.0],
        [-123.0, 45.0]
    ]]
    """
    try:
        _ = location.put_geofence(
            CollectionName=COLLECTION_NAME,
            GeofenceId=geofence_id,
            Geometry={
                "Polygon": polygon_coordinates
            }
        )
        logger.info(
            f"Geofence '{geofence_id}' added to collection "
            f"'{COLLECTION_NAME}'."
        )
        return True
    except ClientError as e:
        logger.exception(f"Failed to add geofence: {e}")
        return False


def create_tracker():
    try:
        location.create_tracker(
            TrackerName=TRACKER_NAME,
            Description="Tracker for user location updates"
        )
        logger.info(f"Tracker '{TRACKER_NAME}' created.")
    except ClientError as e:
        if e.response['Error']['Code'] == "ConflictException":
            logger.exception(
                f"Tracker '{TRACKER_NAME}' already exists."
            )
        else:
            logger.exception(e)


def associate_tracker_to_collection():
    try:
        sts = boto3.client("sts")
        account_id = sts.get_caller_identity()["Account"]
        location.associate_tracker_consumer(
            TrackerName=TRACKER_NAME,
            ConsumerArn=f"arn:aws:geo:{AWS_REGION}:{account_id}:"
                        f"geofence-collection/{COLLECTION_NAME}"
        )
        logger.info("Associated tracker with geofence collection.")
    except ClientError as e:
        if e.response['Error']['Code'] == "ConflictException":
            logger.exception(
                "Tracker already associated with the collection."
            )
        else:
            logger.exception(e)


def update_user_location(user_id, latitude, longitude):
    try:
        location.batch_update_device_position(
            TrackerName=TRACKER_NAME,
            Updates=[{
                "DeviceId": user_id,
                "Position": [longitude, latitude],
                "SampleTime": datetime.now(timezone.utc)
            }]
        )
        logger.info(f"Updated location for user '{user_id}'.")
        return True
    except ClientError as e:
        logger.exception(
            f"Failed to update location for user '{user_id}'.: {e}"
        )
        return False


def create_collection_add_tracker():
    status = create_geofence_collection()
    if not status:
        return None
    create_tracker()
    associate_tracker_to_collection()
    return COLLECTION_NAME


def get_geofence_coordinates(
    collection_name: str, geofence_id: str,
):
    """
    Fetches coordinates of a geofence by ID
    from a given AWS Location Service collection.

    Args:
        collection_name (str): Name of the geofence collection.
        geofence_id (str): ID of the geofence to retrieve.

    Returns:
        list: List of coordinates (longitude, latitude) if found.
        None: If the geofence is not found or an error occurs.
    """
    client = boto3.client("location", region_name=AWS_REGION)

    try:
        response = client.get_geofence(
            CollectionName=collection_name,
            GeofenceId=geofence_id
        )

        polygon = response["Geometry"]["Polygon"]
        return polygon  # This is a list of 1 polygon with a list
        # of points

    except ClientError as e:
        logger.exception(
            f"Error fetching geofence '{geofence_id}':",
            e.response["Error"]["Message"]
        )
        return None
