import io
import torch
import numpy as np
import boto3
from PIL import Image, ImageSequence, ImageOps

def awss3_save_file(client, bucket, key, buff):
    client.put_object(
            Body = buff,
            Key = key, 
            Bucket = bucket)

def awss3_load_file(client, bucket, key):
    outfile = io.BytesIO()
    client.download_fileobj(bucket, key, outfile)
    outfile.seek(0)
    return outfile

def awss3_init_client(region="us-east-1", ak=None, sk=None, session=None):
    client = None
    if (ak == None and sk == None) and session == None:
        client = boto3.client('s3', region_name=region)
    elif (ak != None and sk != None) and session == None:
        client = boto3.client('s3', region_name=region, aws_access_key_id=ak, aws_secret_access_key=sk)
    elif (ak != None and sk != None) and session != None:
        client = boto3.client('s3', region_name=region, aws_access_key_id=ak, aws_secret_access_key=sk, aws_session_token=session)
    else:
        client = boto3.client('s3')
    return client


# SaveImageToS3
class SaveImageToS3:
    @classmethod
    def INPUT_TYPES(s):
        return {"required": { "images": ("IMAGE",), 
                             "region": ("STRING", {"multiline": False, "default": "us-east-1"}),
                             "aws_ak": ("STRING", {"multiline": False, "default": ""}),
                             "aws_sk": ("STRING", {"multiline": False, "default": ""}),
                             "session_token": ("STRING", {"multiline": False, "default": ""}),
                             "s3_bucket": ("STRING", {"multiline": False, "default": "s3_bucket"}),
                             "pathname": ("STRING", {"multiline": False, "default": "pathname for file"}),
                             "format": (['PNG', 'JPEG', 'WebP'], ),
                             "quality": ("INT", {"default": 75, "min": 1, "max": 100}),
                             "optimize": ("BOOLEAN", {"default": False}),
                             "lossless_webp": ("BOOLEAN", {"default": False}),
                             "dpi": ("INT", {"default": 300, "min": 1, "max": 2400, "step": 1}),
                             },
                "hidden": {"prompt": "PROMPT", "extra_pnginfo": "EXTRA_PNGINFO"},
                }
    RETURN_TYPES = ()
    FUNCTION = "save_image_to_s3"
    CATEGORY = "image"
    OUTPUT_NODE = True

    def save_image_to_s3(self, images, region, aws_ak, aws_sk, session_token, s3_bucket, pathname, format, quality, lossless_webp, optimize, dpi, prompt=None, extra_pnginfo=None):
        client = awss3_init_client(region, aws_ak, aws_sk, session_token)
        results = list()
        lossless_webp = (lossless_webp == "true")
        optimize_image = (optimize == "true")

        for (batch_number, image) in enumerate(images):
            i = 255. * image.cpu().numpy()
            img = Image.fromarray(np.clip(i, 0, 255).astype(np.uint8))
            img_byte_arr = io.BytesIO()
            if format == 'JPEG':
                img.save(img_byte_arr,
                         format=format,
                         quality=quality, 
                         optimize=optimize_image, 
                         dpi=(dpi, dpi))
            elif format == 'WebP':
                img.save(img_byte_arr,
                         format=format,
                         quality=quality, 
                         lossless=lossless_webp)
            elif format == 'PNG':
                img.save(img_byte_arr,
                         format=format,
                         optimize=optimize_image)
            img_byte_arr.seek(0)  # Reset buffer position

            awss3_save_file(client, s3_bucket, "%s_%i"%(pathname, batch_number), img_byte_arr)
            results.append({
                "filename": "%s_%i"%(pathname, batch_number),
                "subfolder": "",
                "type": "output"
            })
        return { "ui": { "images": results } }

# LoadImageFromS3
class LoadImageFromS3:
    @classmethod
    def INPUT_TYPES(s):
        return {"required": {"region": ("STRING", {"multiline": False, "default": "us-east-1"}),
                             "aws_ak": ("STRING", {"multiline": False, "default": ""}),
                             "aws_sk": ("STRING", {"multiline": False, "default": ""}),
                             "session_token": ("STRING", {"multiline": False, "default": ""}),
                             "s3_bucket": ("STRING", {"multiline": False, "default": "s3_bucket"}),
                             "pathname": ("STRING", {"multiline": False, "default": "pathname for file"})
                             } 
                }

    RETURN_TYPES = ("IMAGE",)
    OUTPUT_IS_LIST = (False, )
    FUNCTION = "load_image_from_s3"
    CATEGORY = "image"

    def load_image_from_s3(self, region, aws_ak, aws_sk, session_token, s3_bucket, pathname):
        client = awss3_init_client(region, aws_ak, aws_sk, session_token)
        img = Image.open(awss3_load_file(client, s3_bucket, pathname))
        output_images = []
        output_masks = []
        for i in ImageSequence.Iterator(img):
            i = ImageOps.exif_transpose(i)
            if i.mode == 'I':
                i = i.point(lambda i: i * (1 / 255))
            image = i.convert("RGB")
            image = np.array(image).astype(np.float32) / 255.0
            image = torch.from_numpy(image)[None,]
            if 'A' in i.getbands():
                mask = np.array(i.getchannel('A')).astype(np.float32) / 255.0
                mask = 1. - torch.from_numpy(mask)
            else:
                mask = torch.zeros((64,64), dtype=torch.float32, device="cpu")
            output_images.append(image)
            output_masks.append(mask.unsqueeze(0))

        if len(output_images) > 1:
            output_image = torch.cat(output_images, dim=0)
            output_mask = torch.cat(output_masks, dim=0)
        else:
            output_image = output_images[0]
            output_mask = output_masks[0]

        return (output_image, output_mask)

# if __name__ == '__main__':
#     client = awss3_init_client()
#     awss3_save_file(client, "test-bucket", "test.jpg", awss3_load_file(client, "test-bucket", "test"))
