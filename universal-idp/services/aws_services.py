"""AWS service integrations for the Universal IDP application."""

import boto3
import json
from typing import Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)

class AWSServices:
    """Manages AWS service clients and operations."""
    
    def __init__(self, region_name: str = "us-east-1"):
        self.region_name = region_name
        self._bedrock = None
        self._textract = None
        self._s3 = None
    
    @property
    def bedrock(self):
        """Get Bedrock runtime client."""
        if self._bedrock is None:
            self._bedrock = boto3.client("bedrock-runtime", region_name=self.region_name)
        return self._bedrock
    
    @property
    def textract(self):
        """Get Textract client."""
        if self._textract is None:
            self._textract = boto3.client("textract", region_name=self.region_name)
        return self._textract
    
    @property
    def s3_client(self):
        """Get S3 client."""
        if self._s3 is None:
            self._s3 = boto3.client("s3", region_name=self.region_name)
        return self._s3
    
    def call_bedrock(self, prompt: str, text: str, model_id: str, max_tokens: int = 8192) -> str:
        """Call AWS Bedrock with Claude model."""
        try:
            payload = {
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": max_tokens,
                "temperature": 0.2,
                "messages": [
                    {"role": "user", "content": [{"type": "text", "text": f"{prompt}\n\n{text}"}]}
                ],
            }
            
            response = self.bedrock.invoke_model(modelId=model_id, body=json.dumps(payload))
            result = json.loads(response["body"].read())["content"][0]["text"]
            
            logger.info(f"Bedrock call successful, response length: {len(result)}")
            return result
            
        except Exception as e:
            logger.error(f"Bedrock call failed: {str(e)}")
            raise Exception(f"Bedrock API call failed: {str(e)}")
    
    def upload_to_s3(self, bucket: str, key: str, data: bytes, content_type: str = None) -> bool:
        """Upload data to S3."""
        try:
            kwargs = {
                'Bucket': bucket,
                'Key': key,
                'Body': data
            }
            if content_type:
                kwargs['ContentType'] = content_type
            
            self.s3_client.put_object(**kwargs)
            logger.info(f"Uploaded to S3: {key}")
            return True
            
        except Exception as e:
            logger.error(f"S3 upload failed: {str(e)}")
            raise Exception(f"S3 upload failed: {str(e)}")
    
    def get_from_s3(self, bucket: str, key: str) -> Optional[Dict[str, Any]]:
        """Get data from S3."""
        try:
            response = self.s3_client.get_object(Bucket=bucket, Key=key)
            data = json.loads(response['Body'].read().decode('utf-8'))
            logger.info(f"Retrieved from S3: {key}")
            return data
            
        except self.s3_client.exceptions.NoSuchKey:
            logger.info(f"S3 key not found: {key}")
            return None
        except Exception as e:
            logger.error(f"S3 get failed: {str(e)}")
            raise Exception(f"S3 get failed: {str(e)}")
    
    def delete_from_s3(self, bucket: str, key: str) -> bool:
        """Delete data from S3."""
        try:
            self.s3_client.delete_object(Bucket=bucket, Key=key)
            logger.info(f"Deleted from S3: {key}")
            return True
            
        except Exception as e:
            logger.error(f"S3 delete failed: {str(e)}")
            raise Exception(f"S3 delete failed: {str(e)}")

# Global AWS services instance
aws_services = AWSServices()