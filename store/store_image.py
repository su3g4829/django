from openai import OpenAI
import base64

client = OpenAI()

result = client.images.generate(
    model="gpt-image-1",
    prompt="A clean ecommerce product photo of a beige oversized hoodie, front view, white background, soft studio lighting, realistic cotton texture",
    size="1024x1024"
)

image_base64 = result.data[0].b64_json

with open("hoodie.png", "wb") as f:
    f.write(base64.b64decode(image_base64))

print("圖片已輸出：hoodie.png")