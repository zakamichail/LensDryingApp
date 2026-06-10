import math


class RecommendationError(ValueError):
    pass


def calc_center_thickness(h_kraya_mm, d_mm, r1_mm, r2_mm):
    radius_aperture = d_mm / 2.0
    if h_kraya_mm <= 0 or d_mm <= 0:
        raise RecommendationError("Толщина по краю и диаметр линзы должны быть положительными.")
    if abs(r1_mm) <= radius_aperture or abs(r2_mm) <= radius_aperture:
        raise RecommendationError("Модуль каждого радиуса должен быть больше половины диаметра линзы.")

    def sag(r):
        # s(R) = R - sign(R) * sqrt(R^2 - (d/2)^2): стрелка сферической поверхности.
        sign = 1.0 if r >= 0 else -1.0
        return r - sign * math.sqrt(r * r - radius_aperture * radius_aperture)

    # h_c = h_edge + s(R1) - s(R2): центральная толщина линзы.
    center = h_kraya_mm + sag(r1_mm) - sag(r2_mm)
    if center <= 0:
        raise RecommendationError("Расчет не производится: центральная толщина получилась отрицательной или нулевой. Проверьте знаки и значения радиусов.")
    if center <= 0.4:
        raise RecommendationError("Расчет не производится: центральная толщина ниже технологического допуска. Проверьте знаки и значения радиусов.")
    if center > 30.0:
        raise RecommendationError("Расчетная центральная толщина слишком большая. Проверьте радиусы и диаметр.")
    return center
