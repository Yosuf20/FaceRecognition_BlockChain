// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

/// @title PostAnchor
/// @notice Stores content hashes on-chain to create tamper-evident,
///         timestamped records. Each hash is stored alongside the
///         address that submitted it and the block timestamp -- no
///         raw content (images/text) is ever stored, only fingerprints.
contract PostAnchor {
    struct Anchor {
        bytes32 recordHash;
        address submitter;
        uint256 timestamp;
        bool exists;
    }

    // Maps a record hash -> its anchor details.
    mapping(bytes32 => Anchor) public anchors;

    event Anchored(bytes32 indexed recordHash, address indexed submitter, uint256 timestamp);

    /// @notice Anchor a new hash on-chain. Reverts if this exact hash
    ///         was already anchored, to avoid duplicate/confusing records.
    function anchor(bytes32 recordHash) external {
        require(!anchors[recordHash].exists, "PostAnchor: hash already anchored");

        anchors[recordHash] = Anchor({
            recordHash: recordHash,
            submitter: msg.sender,
            timestamp: block.timestamp,
            exists: true
        });

        emit Anchored(recordHash, msg.sender, block.timestamp);
    }

    /// @notice Check whether a given hash has been anchored, and if so,
    ///         return its details for verification.
    function verify(bytes32 recordHash)
        external
        view
        returns (bool found, address submitter, uint256 timestamp)
    {
        Anchor memory a = anchors[recordHash];
        return (a.exists, a.submitter, a.timestamp);
    }
}
