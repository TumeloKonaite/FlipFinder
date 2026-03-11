import os

import boto3

from src.agents.ScannerAgent.deals import Opportunity
from src.agents.agent import Agent


class MessagingAgent(Agent):
    name = "Messaging Agent"
    color = Agent.WHITE
    MODEL = "amazon.nova-micro-v1:0"

    def __init__(self):
        """
        Set up this object to deliver notifications via SNS email and
        generate text with Bedrock.
        """
        self.log("Messaging Agent is initializing")
        self.sns_topic_arn = os.getenv("MESSAGING_SNS_TOPIC_ARN", "").strip()
        self.subject_prefix = os.getenv("MESSAGING_SUBJECT_PREFIX", "Deal Alert").strip()
        self.bedrock_region = (
            os.getenv("MESSAGING_BEDROCK_REGION")
            or os.getenv("BEDROCK_REGION")
            or os.getenv("DEFAULT_AWS_REGION")
            or os.getenv("AWS_REGION")
            or os.getenv("AWS_DEFAULT_REGION")
            or "us-east-1"
        )
        self.model_id = os.getenv("MESSAGING_BEDROCK_MODEL_ID", self.MODEL).strip()
        session = boto3.session.Session(region_name=self.bedrock_region)
        self.bedrock_runtime = session.client("bedrock-runtime")
        self.sns = session.client("sns")
        self.log(
            f"Messaging Agent is ready with delivery=sns model={self.model_id}"
        )

    def _subject_for(self, description: str, discount: float | None = None) -> str:
        compact = " ".join(description.split())
        title = compact[:60].rstrip(" ,.;:-")
        if discount is None:
            return f"{self.subject_prefix}: {title}"[:100]
        return f"{self.subject_prefix}: save ${discount:.0f} on {title}"[:100]

    def push(self, text: str, subject: str | None = None):
        """
        Send a notification via SNS email.
        """
        subject = subject or self.subject_prefix
        if not self.sns_topic_arn:
            raise RuntimeError("MESSAGING_SNS_TOPIC_ARN must be set for SNS delivery")
        self.log("Messaging Agent is publishing to SNS")
        self.sns.publish(TopicArn=self.sns_topic_arn, Subject=subject, Message=text)

    def alert(self, opportunity: Opportunity):
        """
        Make an alert about the specified Opportunity.
        """
        text = f"Deal Alert\n\nPrice: ${opportunity.deal.price:.2f}\n"
        text += f"Estimated value: ${opportunity.estimate:.2f}\n"
        text += f"Estimated discount: ${opportunity.discount:.2f}\n\n"
        text += f"{opportunity.deal.product_description}\n\n{opportunity.deal.url}"
        subject = self._subject_for(
            opportunity.deal.product_description,
            discount=opportunity.discount,
        )
        self.push(text, subject=subject)
        self.log("Messaging Agent has completed")

    def craft_message(
        self, description: str, deal_price: float, estimated_true_value: float
    ) -> str:
        prompt = (
            "Write a short 2-3 sentence notification email about this deal. "
            "Keep it concise and concrete. Mention the offered price, estimated true value, "
            "and why the product is appealing. Do not use markdown or bullet points.\n\n"
            f"Item Description: {description}\n"
            f"Offered Price: {deal_price}\n"
            f"Estimated True Value: {estimated_true_value}"
        )
        response = self.bedrock_runtime.converse(
            modelId=self.model_id,
            messages=[
                {
                    "role": "user",
                    "content": [{"text": prompt}],
                }
            ],
            inferenceConfig={
                "maxTokens": 180,
                "temperature": 0.3,
            },
        )
        content = response["output"]["message"]["content"]
        return "".join(block.get("text", "") for block in content).strip()

    def notify(self, description: str, deal_price: float, estimated_true_value: float, url: str):
        """
        Make an alert about the specified details.
        """
        self.log("Messaging Agent is using Bedrock to craft the message")
        text = self.craft_message(description, deal_price, estimated_true_value)
        full_text = f"{text}\n\n{url}"
        subject = self._subject_for(description, discount=estimated_true_value - deal_price)
        self.push(full_text, subject=subject)
        self.log("Messaging Agent has completed")
