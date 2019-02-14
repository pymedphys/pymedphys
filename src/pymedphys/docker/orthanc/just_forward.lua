function OnStoredInstance(instanceId, tags, metadata)
  Delete(SendToModality(instanceId, 'DoseCHECK'))
end