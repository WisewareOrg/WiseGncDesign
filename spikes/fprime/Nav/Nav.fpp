module Nav {

  array Vector3 = [3] F64
  @ A 3x3 matrix, by rows
  array Matrix3 = [3] Vector3

  @ Holds nav's future parameters; no defaults, so a valid read can only come from the file
  passive component NavPrm {
    @ m^3/s^2, the central body's gravitational parameter
    param mu: F64

    @ The IMU's mounting [PB], v_P = [PB] v_B
    param dcm_PB: Matrix3

    command recv port cmdIn
    command reg port cmdRegOut
    command resp port cmdResponseOut
    param get port prmGetOut
    param set port prmSetOut
  }

}
