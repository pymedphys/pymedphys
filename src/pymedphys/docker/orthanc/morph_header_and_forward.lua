-- Based on https://bitbucket.org/osimis/orthanc-setup-samples/src/c05537f4c4b66dc622356b15c67d40a78fcb476c/docker/transcode-middleman/orthanc-middleman/transcodeAndForward.lua?at=master&fileviewer=file-view-default


function OnStoredInstance(instanceId, tags, metadata, origin)
  -- Do not compress twice the same file
  if origin['RequestOrigin'] ~= 'Lua' then

     -- Retrieve the incoming DICOM instance from Orthanc
     local dicom = RestApiGet('/instances/' .. instanceId .. '/file')

     -- Write the DICOM content to some temporary file
     local received_temp_filepath = instanceId .. '-received.dcm'
     local target = assert(io.open(received_temp_filepath, 'wb'))
     target:write(dicom)
     target:close()

     -- Compress to JPEG2000 using gdcm
     local adjusted_temp_filepath = instanceId .. '-adjusted.dcm'
     os.execute('gdcmconv -U --j2k ' .. uncompressed .. ' ' .. compressed)

     -- Generate a new SOPInstanceUID for the JPEG2000 file, as
     -- gdcmconv does not do this by itself
     os.execute('dcmodify --no-backup -gin ' .. compressed)

     -- Read the JPEG2000 file
     local source = assert(io.open(compressed, 'rb'))
     local jpeg2k = source:read("*all")
     source:close()

     -- Upload the JPEG2000 file and remove the uncompressed file
     local jpeg2kInstance = ParseJson(RestApiPost('/instances', jpeg2k))
     RestApiDelete('/instances/' .. instanceId)

     -- Remove the temporary DICOM files
     os.remove(uncompressed)
     os.remove(compressed)

     print(instanceId)
     PrintRecursive(jpeg2kInstance)
     print(jpeg2kInstance['ID'])
     -- forward to the PACS and delete
   Delete(SendToModality(jpeg2kInstance['ID'], 'pacs'))

  end
end