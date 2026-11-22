@ Gives navigation its state, as of the FSW time it applies at
sync command initNavState(
  epoch: F64 @< s, the FSW time the state applies at
  attitude: Gnc.Quaternion @< body to ECI, W X Y Z
  position: Gnc.Vector3 @< m, body position in ECI
  velocity: Gnc.Vector3 @< m/s, body velocity in ECI
)
