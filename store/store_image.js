import OpenAI from "openai";
import fs from "fs";

const client = new OpenAI({
  apiKey: process.env.OPENAI_API_KEY,
});

const result = await client.images.generate({
  model: "gpt-image-1",
  prompt: "A clean ecommerce product photo of a beige oversized hoodie, front view, white background, soft studio lighting",
  size: "1024x1024",
});

const imageBase64 = result.data[0].b64_json;
fs.writeFileSync("hoodie.png", Buffer.from(imageBase64, "base64"));