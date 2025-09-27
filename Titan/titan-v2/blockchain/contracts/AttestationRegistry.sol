// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

contract AttestationRegistry {
    event Attested(bytes32 indexed docHash, address indexed subject, string verifierId, uint256 timestamp);

    struct Attestation {
        bytes32 docHash;
        address subject;
        string verifierId;
        uint256 timestamp;
    }

    mapping(bytes32 => Attestation) public attestations;

    function attest(bytes32 docHash, address subject, string calldata verifierId) external {
        require(docHash != bytes32(0), "invalid hash");
        Attestation memory a = Attestation({
            docHash: docHash,
            subject: subject,
            verifierId: verifierId,
            timestamp: block.timestamp
        });
        attestations[docHash] = a;
        emit Attested(docHash, subject, verifierId, block.timestamp);
    }

    function get(bytes32 docHash) external view returns (Attestation memory) {
        return attestations[docHash];
    }
}
