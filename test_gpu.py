import torch

def main():
    print(f"PyTorch Version: {torch.__version__}")
    print(f"CUDA Available:  {torch.cuda.is_available()}")
    if torch.cuda.is_available():
        print(f"GPU Device:      {torch.cuda.get_device_name(0)}")
        print(f"CUDA Capability: {torch.cuda.get_device_capability(0)}")
        
        # Test tensor calculation
        x = torch.randn(1000, 1000, device="cuda")
        y = torch.randn(1000, 1000, device="cuda")
        z = torch.matmul(x, y)
        print(f"CUDA Computation Successful! Output shape: {z.shape}")
        print(f"Allocated VRAM: {round(torch.cuda.memory_allocated() / (1024 ** 2), 2)} MB")
    else:
        print("Running on CPU.")

if __name__ == "__main__":
    main()
