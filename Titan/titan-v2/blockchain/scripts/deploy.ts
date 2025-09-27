import { ethers } from "hardhat";
import { writeFileSync } from "fs";

async function main() {
  const Registry = await ethers.getContractFactory("AttestationRegistry");
  const registry = await Registry.deploy();
  await registry.waitForDeployment();
  const addr = await registry.getAddress();
  console.log("AttestationRegistry:", addr);
  writeFileSync("registry_address.txt", addr);
}
main().catch((e) => { console.error(e); process.exit(1); });
